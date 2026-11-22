"""Scripted tool-calling model. Same loop as a live model. No network and no key.

It does not invent quantities. Intake fields come from the text parser. Menu ids come
from the price-book rules. The quote sentence copies numbers the pricing tool returned.
"""

import json

from handa.engine.intake import parse_request, questions_for
from handa.engine.ops import resolve_menu_ids
from handa.llm.base import Completion, ToolCall
from handa.sample_data.generate import generate_catalog
from handa.schemas import EventRequest


class MockModel:
    provider = "mock"
    model = "mock"

    def __init__(self):
        self._n = 0

    def complete(self, *, agent: str, messages: list[dict], tools: list[dict] | None = None) -> Completion:
        self._n += 1
        called = [message.get("name") for message in messages if message.get("role") == "tool"]
        if agent == "intake":
            return self._intake(messages, called)
        if agent == "menu":
            return self._menu(messages, called)
        if agent == "pricing":
            return self._pricing(messages, called)
        return Completion(content=json.dumps({"message": "Nothing to add."}))

    def _intake(self, messages: list[dict], called: list[str]) -> Completion:
        if "submit_event" not in called:
            event = parse_request(_user_text(messages))
            return Completion(
                tool_calls=[ToolCall(id=f"mock-{self._n}", name="submit_event", arguments=_dump(event))]
            )
        payload = _tool_json(messages, "submit_event")
        missing = payload.get("missing") or []
        follow = " ".join(questions_for(missing)) if missing else ""
        note = "Read the request and filed the fields the text actually contained."
        if missing:
            note = "Filed what was present. A required field is still missing, so I am asking."
        return Completion(content=json.dumps({"note": note, "follow_up": follow}))

    def _menu(self, messages: list[dict], called: list[str]) -> Completion:
        brief = _context(messages)
        if "search_recipes" not in called:
            exclude = " ".join(brief.get("exclude") or [])
            return Completion(
                tool_calls=[
                    ToolCall(
                        id=f"mock-{self._n}",
                        name="search_recipes",
                        arguments={"query": f"{brief.get('event_type', '')} {exclude} portion budget".strip()},
                    )
                ]
            )
        if "check_diet" not in called:
            return Completion(
                tool_calls=[
                    ToolCall(
                        id=f"mock-{self._n}",
                        name="check_diet",
                        arguments={"recipe_ids": _candidate_ids(messages), "exclude": brief.get("exclude") or []},
                    )
                ]
            )
        if "get_budget_per_head" not in called:
            return Completion(
                tool_calls=[
                    ToolCall(
                        id=f"mock-{self._n}",
                        name="get_budget_per_head",
                        arguments={"budget_php": brief.get("budget_php"), "guests": brief.get("guests")},
                    )
                ]
            )
        ids = resolve_menu_ids(
            brief,
            int(brief.get("revision") or 0),
            generate_catalog(),
            brief.get("avoid") or [],
        )
        rationale = "Chose the price-book spread that fits the diet tags and the per-head budget from the tools."
        if int(brief.get("revision") or 0) >= 1:
            rationale = "The quote was over budget, so this pass swaps the premium dishes for the house alternates."
        return Completion(content=json.dumps({"recipe_ids": ids, "rationale": rationale, "swaps": brief.get("swaps") or []}))

    def _pricing(self, messages: list[dict], called: list[str]) -> Completion:
        if "read_quote" not in called:
            return Completion(tool_calls=[ToolCall(id=f"mock-{self._n}", name="read_quote", arguments={})])
        quote = _tool_json(messages, "read_quote")
        summary = (
            f"For {quote.get('guests')} guests, the package is PHP {quote.get('quote_php'):,.2f} "
            f"against a budget of PHP {quote.get('budget_php'):,.2f}."
        )
        return Completion(content=json.dumps({"summary": summary}))


def _user_text(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") == "user":
            return message.get("content") or ""
    return ""


def _tool_json(messages: list[dict], name: str) -> dict:
    for message in reversed(messages):
        if message.get("role") == "tool" and message.get("name") == name:
            return json.loads(message.get("content") or "{}")
    return {}


def _context(messages: list[dict]) -> dict:
    text = _user_text(messages)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        return {}
    return json.loads(text[start : end + 1])


def _candidate_ids(messages: list[dict]) -> list[str]:
    payload = _tool_json(messages, "search_recipes")
    return [row["id"] for row in payload.get("candidates") or []][:8]


def _dump(event: EventRequest) -> dict:
    data = event.model_dump(mode="json")
    data.pop("raw_text", None)
    data.pop("notes", None)
    return data
