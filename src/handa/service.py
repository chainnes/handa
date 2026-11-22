"""Run the desk, stream handoffs, and rerun only the nodes a disruption touches."""

from __future__ import annotations

from threading import Condition, Thread
from uuid import uuid4
import logging

from langgraph.types import Command

from handa.config import Settings, get_settings
from handa.errors import DeskError, ProviderError
from handa.graph.build import build_graph
from handa.llm.factory import build_model
from handa.rag.index import KnowledgeIndex
from handa.sample_data.generate import generate_catalog

log = logging.getLogger("handa.service")


class Desk:
    def __init__(self, graph, catalog, index, settings: Settings):
        self.graph = graph
        self.catalog = catalog
        self.index = index
        self.settings = settings
        self._runs: dict[str, dict] = {}

    @classmethod
    def create(cls, settings: Settings | None = None) -> "Desk":
        settings = settings or get_settings()
        catalog = generate_catalog()
        index = KnowledgeIndex(settings)
        index.ensure()
        model = build_model(settings)
        graph = build_graph(catalog, index, settings, model)
        log.info(
            "desk ready provider=%s recipes=%s suppliers=%s",
            settings.provider_label,
            len(catalog["recipes"]),
            len(catalog["suppliers"]),
        )
        return cls(graph, catalog, index, settings)

    def begin(self, text: str) -> str:
        run_id = uuid4().hex[:12]
        self._runs[run_id] = self._blank()
        state = {
            "run_id": run_id,
            "raw_text": text,
            "event": None,
            "missing": [],
            "revision": 0,
            "avoid": [],
            "menu": None,
            "inventory": None,
            "procurement": None,
            "logistics": None,
            "pricing": None,
            "status": "running",
            "alternatives": [],
            "supplier_overrides": {},
            "inventory_overrides": {},
            "review": False,
            "agent_messages": [],
        }
        self._start(run_id, state, resume=False)
        log.info("run start id=%s", run_id)
        return run_id

    def reply(self, run_id: str, answer) -> None:
        self._require(run_id)
        if self._runs[run_id]["thread"] and self._runs[run_id]["thread"].is_alive():
            raise DeskError("This run is still working.", 409)
        if not self.view(run_id)["pending"]:
            raise DeskError("This run is not waiting for an answer.", 409)
        self._runs[run_id]["paused"] = False
        self._start(run_id, answer, resume=True)

    def disrupt(self, run_id: str, kind: str) -> None:
        record = self._require(run_id)
        if record["thread"] and record["thread"].is_alive():
            raise DeskError("This run is still working.", 409)
        view = self.view(run_id)
        if view["pending"]:
            raise DeskError("Answer the intake questions before simulating a disruption.", 409)
        if not view.get("pricing"):
            raise DeskError("There is no priced file to disrupt yet.", 409)
        config = _config(run_id)
        values = self.graph.get_state(config).values
        note = {
            "id": uuid4().hex[:8],
            "from_agent": "desk",
            "to_agent": _DISRUPT_TARGET[kind],
            "summary": _DISRUPT_TEXT[kind],
            "tone": "warn",
        }
        if kind == "extra_guests":
            event = dict(values["event"])
            event["guests"] = int(event["guests"]) + 15
            patch = {"event": event, "revision": 0, "avoid": [], "agent_messages": [note]}
            as_node = "intake"
        elif kind == "spoilage":
            overrides = dict(values.get("inventory_overrides") or {})
            for line in values["inventory"]["lines"]:
                if line["perishable"]:
                    overrides[line["ingredient_id"]] = 0
            patch = {"inventory_overrides": overrides, "agent_messages": [note]}
            as_node = "menu"
        elif kind == "supplier_delay":
            overrides = dict(values.get("supplier_overrides") or {})
            overrides["balintawak"] = int(overrides.get("balintawak", 0)) + 30
            patch = {"supplier_overrides": overrides, "agent_messages": [note]}
            as_node = "inventory"
        else:
            raise DeskError("Unknown disruption. Use supplier_delay, spoilage, or extra_guests.", 400)
        self.graph.update_state(config, patch, as_node=as_node)
        record["paused"] = False
        record["done"] = False
        self._push(run_id, {"type": "message", "message": note})
        self._start(run_id, None, resume=False, cont=True)
        log.info("disruption id=%s kind=%s", run_id, kind)

    def decide(self, run_id: str, action: str, notes: str = "") -> dict:
        view = self.view(run_id)
        if view["pending"]:
            raise DeskError("The intake questions are still open.", 409)
        status = view["status"]
        if action == "cancel":
            issued = "cancelled"
        elif action == "issue" and status == "pass":
            issued = "issued"
        elif action == "issue" and status == "over_budget":
            issued = "issued_over_budget"
        elif action == "acknowledge" and status in {"review_queue", "infeasible"}:
            issued = status
        else:
            raise DeskError(f"Cannot {action} a file that is {status}.", 409)
        self._runs[run_id]["decision"] = {"action": action, "notes": notes, "status": issued}
        log.info("decision id=%s action=%s", run_id, action)
        return self.view(run_id)

    def wait(self, run_id: str, timeout: float = 20) -> dict:
        thread = self._require(run_id)["thread"]
        if thread:
            thread.join(timeout)
        return self.view(run_id)

    def view(self, run_id: str) -> dict:
        self._require(run_id)
        snapshot = self.graph.get_state(_config(run_id))
        values = snapshot.values or {}
        pending = _interrupt_value(snapshot)
        if not values:
            return {
                "run_id": run_id,
                "status": "running",
                "event": None,
                "missing": [],
                "questions": [],
                "revision": 0,
                "menu": None,
                "inventory": None,
                "procurement": None,
                "logistics": None,
                "pricing": None,
                "alternatives": [],
                "agent_messages": [],
                "pending": None,
                "error": self._runs[run_id].get("error"),
                "decision": self._runs[run_id].get("decision"),
                "currency_note": self.catalog["currency_note"],
            }
        status = values.get("status") or "running"
        decision = self._runs[run_id].get("decision")
        if decision and not pending:
            status = decision["status"]
        if pending:
            status = "awaiting_intake"
        return {
            "run_id": run_id,
            "status": status,
            "event": values.get("event"),
            "missing": (pending or {}).get("missing") or values.get("missing") or [],
            "questions": (pending or {}).get("questions") or [],
            "revision": int(values.get("revision") or 0),
            "menu": values.get("menu"),
            "inventory": values.get("inventory"),
            "procurement": values.get("procurement"),
            "logistics": values.get("logistics"),
            "pricing": values.get("pricing"),
            "alternatives": values.get("alternatives") or [],
            "agent_messages": values.get("agent_messages") or [],
            "pending": pending,
            "error": self._runs[run_id].get("error"),
            "decision": decision,
            "currency_note": self.catalog["currency_note"],
        }

    def iter_events(self, run_id: str):
        record = self._require(run_id)
        cursor = 0
        while True:
            with record["cv"]:
                batch = record["events"][cursor:]
                cursor = len(record["events"])
                finished = record["done"] and not record["paused"]
                if not batch and not finished:
                    record["cv"].wait(timeout=0.5)
                    continue
            for item in batch:
                yield item
            if finished:
                return

    def _start(self, run_id: str, payload, resume: bool, cont: bool = False) -> None:
        thread = Thread(target=self._execute, args=(run_id, payload, resume, cont), daemon=True)
        self._runs[run_id]["thread"] = thread
        self._runs[run_id]["done"] = False
        thread.start()

    def _execute(self, run_id: str, payload, resume: bool, cont: bool) -> None:
        config = _config(run_id)
        try:
            if cont:
                stream = self.graph.stream(None, config, stream_mode="updates")
            elif resume:
                stream = self.graph.stream(Command(resume=payload), config, stream_mode="updates")
            else:
                stream = self.graph.stream(payload, config, stream_mode="updates")
            for chunk in stream:
                for _node, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    for message in update.get("agent_messages") or []:
                        self._push(run_id, {"type": "message", "message": message})
        except ProviderError as exc:
            self._runs[run_id]["error"] = exc.message
            self._push(run_id, {"type": "error", "error": exc.message})
        except Exception as exc:
            log.exception("run failed id=%s", run_id)
            self._runs[run_id]["error"] = str(exc)
            self._push(run_id, {"type": "error", "error": "The desk could not finish this brief."})
        view = self.safe_view(run_id)
        pending = view.get("pending") if view else None
        self._runs[run_id]["paused"] = bool(pending)
        self._runs[run_id]["done"] = not bool(pending)
        if view:
            self._push(run_id, {"type": "state", "view": view})
        self._push(run_id, {"type": "pause" if pending else "done", "view": view})
        with self._runs[run_id]["cv"]:
            self._runs[run_id]["cv"].notify_all()

    def safe_view(self, run_id: str) -> dict | None:
        try:
            return self.view(run_id)
        except DeskError:
            return None

    def _push(self, run_id: str, event: dict) -> None:
        record = self._runs[run_id]
        with record["cv"]:
            record["events"].append(event)
            record["cv"].notify_all()

    def _require(self, run_id: str) -> dict:
        record = self._runs.get(run_id)
        if record is None:
            raise DeskError("No run with that id. A restart clears open files.", 404)
        return record

    def _blank(self) -> dict:
        return {"events": [], "done": False, "paused": False, "thread": None, "error": None, "decision": None, "cv": Condition()}


_DISRUPT_TARGET = {"extra_guests": "menu", "spoilage": "inventory", "supplier_delay": "procurement"}
_DISRUPT_TEXT = {
    "extra_guests": "Disruption: 15 more guests. Repricing from the menu. Earlier nodes stay as they were.",
    "spoilage": "Disruption: perishable stock was written off. Renetting inventory, then buying again.",
    "supplier_delay": "Disruption: Balintawak is 30 days slower. Rechecking suppliers from procurement.",
}


def _config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}, "recursion_limit": 50}


def _interrupt_value(snapshot) -> dict | None:
    for task in getattr(snapshot, "tasks", None) or []:
        for item in getattr(task, "interrupts", None) or []:
            value = getattr(item, "value", None)
            if isinstance(value, dict):
                return value
    return None
