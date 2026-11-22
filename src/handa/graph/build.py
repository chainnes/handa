"""intake → menu → inventory → procurement → logistics → pricing, with a pricing⇄menu loop.

Intake, menu, and the client summary are LLM turns. They call tools.
Quantities, pesos, and clock times stay in the Python tools.
"""

from operator import add
from typing import Annotated, TypedDict
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from handa.agents.repair import accept_schema, repair_handoff
from handa.agents.roles import choose_with_model, parse_with_model, summarize_with_model
from handa.config import Settings
from handa.engine.intake import apply_answer, missing_fields, questions_for
from handa.engine.ops import (
    _diet_ok,
    build_inventory,
    build_logistics,
    build_menu,
    build_pricing,
    build_procurement,
    resolve_menu_ids,
)
from handa.schemas import AgentMessage, EventRequest, Handoff


class DeskState(TypedDict, total=False):
    run_id: str
    raw_text: str
    event: dict | None
    missing: list[str]
    revision: int
    avoid: list[str]
    menu: dict | None
    inventory: dict | None
    procurement: dict | None
    logistics: dict | None
    pricing: dict | None
    status: str
    alternatives: list[str]
    supplier_overrides: dict
    inventory_overrides: dict
    review: bool
    agent_messages: Annotated[list[dict], add]


def build_graph(catalog: dict, index, settings: Settings, model, checkpointer=None):
    max_revisions = settings.max_revisions
    model_name = getattr(model, "model", None) or getattr(model, "provider", "mock")

    def handoff(source: str, target: str, summary: str, tone: str = "info", source_kind: str = "python") -> dict:
        checked, review = accept_schema({"message": summary}, Handoff, repair_handoff)
        text = checked.message if checked else (summary[:400] or "The desk could not phrase this step.")
        message = AgentMessage(
            id=uuid4().hex[:8],
            from_agent=source,
            to_agent=target,
            summary=text,
            tone=tone,  # type: ignore[arg-type]
            source=source_kind,  # type: ignore[arg-type]
            model=model_name if source_kind == "llm" else "",
        ).model_dump()
        update: dict = {"agent_messages": [message]}
        if review:
            update["review"] = True
            update["status"] = "review_queue"
        return update

    def tool_notes(agent: str, records: list[dict]) -> list[dict]:
        notes = []
        for record in records:
            result = record["result"]
            if record["name"] == "submit_event":
                detail = "filed the brief" if result.get("ok") else f"rejected the fields: {result.get('error', '')[:180]}"
            elif record["name"] == "search_recipes":
                detail = f"{len(result.get('candidates') or [])} diet-safe dishes"
            elif record["name"] == "check_diet":
                blocked = [row["id"] for row in result.get("results") or [] if not row.get("ok")]
                detail = "all allowed" if not blocked else "blocked " + ", ".join(blocked)
            elif record["name"] == "get_budget_per_head":
                detail = f"PHP {result.get('per_head_php')} per guest"
            elif record["name"] == "read_quote":
                detail = f"quote PHP {result.get('quote_php')}"
            else:
                detail = record["name"]
            notes.append(
                AgentMessage(
                    id=uuid4().hex[:8],
                    from_agent=agent,
                    to_agent=record["name"],
                    summary=f"Tool {record['name']}: {detail}.",
                    tone="warn" if result.get("ok") is False else "info",
                    source="tool",
                ).model_dump()
            )
        return notes

    def intake_node(state: DeskState) -> dict:
        text = state.get("raw_text") or ""
        event = EventRequest.model_validate(state["event"]) if state.get("event") else None
        notes: list[dict] = []
        review = bool(state.get("review"))
        follow = ""
        # The node restarts after each answer, so re-parse the text accumulated so far.
        while True:
            parsed, follow_up, records, bad, _note = parse_with_model(model, text)
            notes.extend(tool_notes("intake", records))
            if bad or parsed is None:
                review = True
                notes.append(
                    handoff(
                        "intake",
                        "review",
                        "The intake model did not return a valid event after one repair. The file is in the review queue.",
                        "bad",
                        "llm",
                    )["agent_messages"][0]
                )
                return {"status": "review_queue", "review": True, "agent_messages": notes, "missing": missing_fields(event) if event else ["event_type"]}
            if parsed is not None:
                event = _merge_event(event, parsed)
            missing = missing_fields(event) if event else ["event_type", "guests", "event_date", "event_time", "city", "budget_php"]
            follow = follow_up or " ".join(questions_for(missing))
            if not missing:
                break
            answer = interrupt(
                {
                    "kind": "intake",
                    "missing": missing,
                    "questions": [follow] if follow else questions_for(missing),
                    "draft": event.model_dump(mode="json") if event else {},
                }
            )
            if isinstance(answer, dict) and answer.get("action") == "cancel":
                notes.append(handoff("intake", "done", "The brief was cancelled before it was priced.", "warn", "python")["agent_messages"][0])
                return {
                    "event": event.model_dump(mode="json") if event else None,
                    "missing": missing,
                    "status": "cancelled",
                    "agent_messages": notes,
                }
            event = apply_answer(event or EventRequest(raw_text=text), answer)
            text = _extend_text(text, answer)
            missing = missing_fields(event)
            if not missing:
                break
        assert event is not None
        done = handoff(
            "intake",
            "menu",
            f"LLM filed the brief for {event.guests} guests in {event.city}. Sending it to menu.",
            "ok",
            "llm",
        )
        notes.extend(done["agent_messages"])
        return {
            "event": event.model_dump(mode="json"),
            "missing": [],
            "status": "review_queue" if review else "running",
            "review": review,
            "raw_text": text,
            "agent_messages": notes,
        }

    def menu_node(state: DeskState) -> dict:
        event = state["event"]
        revision = int(state.get("revision") or 0)
        avoid = list(state.get("avoid") or [])
        choice, records, review = choose_with_model(model, catalog, index, event, revision, avoid)
        notes = tool_notes("menu", records)
        ids, fell_back = _lock_ids(choice, event, revision, catalog, avoid)
        menu = build_menu(event, revision, catalog, avoid, recipe_ids=ids)
        query = f"{event.get('event_type', '')} menu"
        menu["citations"] = index.search(query, k=3) if index is not None else []
        rationale = choice.rationale if choice else "The price book chose the menu."
        menu["rationale"] = rationale
        if fell_back:
            menu["warnings"] = list(menu["warnings"]) + [
                "The model selection was incomplete or broke the diet rule, so the price-book menu was used."
            ]
        if review:
            notes.append(
                handoff(
                    "menu",
                    "inventory",
                    "The menu model failed schema validation after one repair. The price-book menu was used and the file is queued for review.",
                    "bad",
                    "llm",
                )["agent_messages"][0]
            )
        else:
            notes.append(
                handoff("menu", "inventory", f"LLM menu pass {revision}: {rationale}", "info", "llm")["agent_messages"][0]
            )
        update = {"menu": menu, "agent_messages": notes}
        if review:
            update["review"] = True
        return update

    def inventory_node(state: DeskState) -> dict:
        stock = build_inventory(state["menu"], catalog, state.get("inventory_overrides") or {})
        short = sum(1 for line in stock["lines"] if line["shortfall"] > 0)
        note = handoff("inventory", "procurement", f"Netted stock. {short} ingredient line(s) still need buying.")
        return {"inventory": stock, **note}

    def procurement_node(state: DeskState) -> dict:
        bought = build_procurement(
            state["inventory"],
            state["event"],
            catalog,
            state.get("supplier_overrides") or {},
        )
        switches = [line["name"] for line in bought["lines"] if line.get("switched_from")]
        tone = "bad" if bought["infeasible"] else ("warn" if switches else "ok")
        summary = f"Purchase list is PHP {bought['purchase_php']:,.2f}."
        if switches:
            summary += " Switched supplier for " + ", ".join(switches) + "."
        if bought["infeasible"]:
            summary += " " + bought["alternatives"][0]
        target = "logistics" if not bought["infeasible"] else "pricing"
        note = handoff("procurement", target, summary, tone)
        return {"procurement": bought, "alternatives": bought["alternatives"], **note}

    def logistics_node(state: DeskState) -> dict:
        plan = build_logistics(state["menu"], state["procurement"], state["event"])
        first = plan["timeline"][0]["task"] if plan["timeline"] else "timeline"
        note = handoff("logistics", "pricing", f"Backward schedule starts at {first}. Crew is on the file.")
        return {"logistics": plan, **note}

    def pricing_node(state: DeskState) -> dict:
        revision = int(state.get("revision") or 0)
        priced = build_pricing(state["menu"], state["procurement"], state["event"], revision, max_revisions)
        summary, records, review = summarize_with_model(model, priced, int(state["event"]["guests"]))
        notes = tool_notes("pricing", records)
        if summary:
            priced["client_summary"] = summary
        else:
            priced["client_summary"] = priced["guidance"]
            if review:
                notes.append(
                    handoff(
                        "pricing",
                        "review",
                        "The quote sentence was rejected because it did not match the schema or it invented a number. The tool totals stand.",
                        "bad",
                        "llm",
                    )["agent_messages"][0]
                )
        if state.get("review") or review:
            priced["status"] = "review_queue" if priced["status"] == "pass" else priced["status"]
            # A failed summary on an otherwise good file still needs a person.
            if review and priced["status"] == "pass":
                priced["status"] = "review_queue"
        if review or state.get("review"):
            if priced["status"] == "pass":
                priced["status"] = "review_queue"
        tone = {"pass": "ok", "revise": "warn", "over_budget": "bad", "infeasible": "bad", "review_queue": "warn"}.get(
            priced["status"], "info"
        )
        target = "menu" if priced["status"] == "revise" else "done"
        sentence = priced.get("client_summary") or priced["guidance"]
        notes.append(
            handoff(
                "pricing",
                target,
                f"Quote PHP {priced['quote_php']:,.2f} against PHP {priced['budget_php']:,.2f}. {sentence}",
                tone,
                "llm",
            )["agent_messages"][0]
        )
        update = {"pricing": priced, "status": priced["status"], "agent_messages": notes}
        if review or state.get("review"):
            update["review"] = True
        if priced["status"] == "revise":
            update["revision"] = revision + 1
            if state["procurement"].get("infeasible"):
                update["avoid"] = [line["ingredient_id"] for line in state["procurement"]["lines"] if line.get("infeasible")]
        if priced["status"] == "infeasible" and revision < max_revisions:
            avoid = [line["ingredient_id"] for line in state["procurement"]["lines"] if line.get("infeasible")]
            if avoid and avoid != list(state.get("avoid") or []):
                update["status"] = "revise"
                update["revision"] = revision + 1
                update["avoid"] = avoid
                update["pricing"] = {**priced, "status": "revise", "guidance": "Dropping dishes no supplier can deliver, then repricing."}
        return update

    graph = StateGraph(DeskState)
    graph.add_node("intake", intake_node)
    graph.add_node("menu", menu_node)
    graph.add_node("inventory", inventory_node)
    graph.add_node("procurement", procurement_node)
    graph.add_node("logistics", logistics_node)
    graph.add_node("pricing", pricing_node)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake",
        lambda state: "end" if state.get("status") in {"cancelled", "review_queue"} else "menu",
        {"menu": "menu", "end": END},
    )
    graph.add_edge("menu", "inventory")
    graph.add_edge("inventory", "procurement")
    graph.add_edge("procurement", "logistics")
    graph.add_edge("logistics", "pricing")
    graph.add_conditional_edges(
        "pricing",
        lambda state: "menu" if state.get("status") == "revise" else "end",
        {"menu": "menu", "end": END},
    )
    return graph.compile(checkpointer=checkpointer or InMemorySaver())


def _merge_event(current: EventRequest | None, parsed: EventRequest) -> EventRequest:
    if current is None:
        return parsed
    data = current.model_dump()
    incoming = parsed.model_dump()
    for key, value in incoming.items():
        if data.get(key) in (None, "", []) and value not in (None, "", []):
            data[key] = value
    for rule in incoming.get("exclude") or []:
        if rule not in data["exclude"]:
            data["exclude"].append(rule)
    return EventRequest.model_validate(data)


def _extend_text(text: str, answer) -> str:
    if isinstance(answer, dict):
        bits = [f"{key} {value}" for key, value in answer.items() if key != "action"]
        return text + "\n" + " ".join(bits)
    return text + "\n" + str(answer)


def _lock_ids(choice, event, revision, catalog, avoid) -> tuple[list[str], bool]:
    fallback = resolve_menu_ids(event, revision, catalog, avoid)
    if choice is None:
        return fallback, True
    recipes = {recipe["id"]: recipe for recipe in catalog["recipes"]}
    exclude = list(event.get("exclude") or [])
    ids = []
    for recipe_id in choice.recipe_ids:
        recipe = recipes.get(recipe_id)
        if recipe is None:
            continue
        if not _diet_ok(recipe, exclude):
            continue
        ids.append(recipe_id)
    if len(ids) < 3:
        return fallback, True
    return ids, False
