"""Recorded model replies. No network."""

import json

from handa.agents.roles import choose_with_model, parse_with_model, summarize_with_model
from handa.llm.base import Completion, ToolCall
from handa.sample_data.generate import generate_catalog


class ScriptedModel:
    provider = "recorded"
    model = "recorded"

    def __init__(self, script):
        self.script = list(script)

    def complete(self, *, agent, messages, tools=None):
        if not self.script:
            raise AssertionError(f"script ran out during {agent}")
        return self.script.pop(0)


def test_menu_agent_calls_tools_then_repairs_a_bad_choice():
    catalog = generate_catalog()
    event = {
        "event_type": "corporate",
        "guests": 60,
        "budget_php": 45000,
        "exclude": ["pork"],
        "vegetarian_guests": 8,
        "city": "Taguig",
    }
    model = ScriptedModel(
        [
            Completion(tool_calls=[ToolCall(id="1", name="search_recipes", arguments={"query": "corporate no pork"})]),
            Completion(tool_calls=[ToolCall(id="2", name="check_diet", arguments={"recipe_ids": ["garlic_rice", "lechon_belly"]})]),
            Completion(tool_calls=[ToolCall(id="3", name="get_budget_per_head", arguments={"budget_php": 45000, "guests": 60})]),
            Completion(content=json.dumps({"recipe_ids": "not-a-list", "rationale": "bad"})),
            Completion(
                content=json.dumps(
                    {
                        "recipe_ids": ["garlic_rice", "chicken_afritada", "chopsuey", "buko_pandan", "iced_tea"],
                        "rationale": "House buffet, no pork, after the diet check.",
                        "swaps": [],
                    }
                )
            ),
        ]
    )
    choice, records, review = choose_with_model(model, catalog, index=None, event=event, revision=0, avoid=[])
    assert review is False
    assert [record["name"] for record in records] == ["search_recipes", "check_diet", "get_budget_per_head"]
    assert choice.recipe_ids[0] == "garlic_rice"
    diet = next(record for record in records if record["name"] == "check_diet")
    blocked = [row["id"] for row in diet["result"]["results"] if not row["ok"]]
    assert "lechon_belly" in blocked
    assert model.script == []


def test_a_second_bad_payload_goes_to_review():
    catalog = generate_catalog()
    event = {"event_type": "corporate", "guests": 40, "budget_php": 20000, "exclude": [], "vegetarian_guests": 0}
    model = ScriptedModel(
        [
            Completion(content="not json"),
            Completion(content=json.dumps({"recipe_ids": []})),
        ]
    )
    choice, _records, review = choose_with_model(model, catalog, index=None, event=event, revision=0, avoid=[])
    assert choice is None
    assert review is True


def test_quote_summary_that_invents_a_total_is_rejected():
    priced = {
        "quote_php": 1000.0,
        "budget_php": 2000.0,
        "gap_php": -1000.0,
        "food_php": 400.0,
        "purchase_php": 300.0,
        "service_php": 200.0,
        "equipment_php": 100.0,
        "travel_php": 0.0,
        "overhead_php": 50.0,
        "status": "pass",
        "guidance": "The quote fits the budget.",
    }
    model = ScriptedModel(
        [
            Completion(tool_calls=[ToolCall(id="q", name="read_quote", arguments={})]),
            Completion(content=json.dumps({"summary": "The package is PHP 99999.00 for the night."})),
        ]
    )
    text, records, review = summarize_with_model(model, priced, guests=40)
    assert records[0]["name"] == "read_quote"
    assert text == ""
    assert review is True


def test_intake_repairs_a_rejected_event_then_asks():
    model = ScriptedModel(
        [
            Completion(tool_calls=[ToolCall(id="a", name="submit_event", arguments={"guests": "many"})]),
            Completion(
                tool_calls=[
                    ToolCall(
                        id="b",
                        name="submit_event",
                        arguments={"event_type": "debut", "guests": 120, "city": "Antipolo"},
                    )
                ]
            ),
            Completion(
                content=json.dumps(
                    {
                        "note": "Filed the debut. The budget and the date are still missing.",
                        "follow_up": "What is the budget in pesos?",
                    }
                )
            ),
        ]
    )
    event, follow, records, review, _note = parse_with_model(model, "debut for 120 guests in Antipolo")
    assert review is False
    assert records[0]["result"]["ok"] is False
    assert records[1]["result"]["ok"] is True
    assert event.guests == 120
    assert "budget_php" in records[1]["result"]["missing"]
    assert "budget" in follow.lower()
