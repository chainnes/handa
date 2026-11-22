"""LLM roles. Tools compute. The model only parses, chooses, and phrases."""

import json
import re

from handa.agents.loop import run_agent
from handa.engine.intake import missing_fields, questions_for
from handa.engine.money import D, pesos
from handa.engine.ops import _book_cost, _diet_ok, _index
from handa.schemas import EventRequest, IntakeNote, MenuChoice, QuoteSummary

INTAKE_SYSTEM = (
    "You are the intake clerk at Mesa Clara Catering in Quezon City. "
    "Call submit_event with only the fields the guest actually wrote. "
    "Do not invent a guest count, a date, a city, or a budget. "
    "Then reply with JSON {\"note\": string, \"follow_up\": string}. "
    "follow_up is the question you will ask if something required is missing, otherwise an empty string. "
    "Do not put peso amounts in the note."
)

MENU_SYSTEM = (
    "You are the menu planner at Mesa Clara. Call search_recipes, check_diet, and get_budget_per_head "
    "before you choose. Reply with JSON {\"recipe_ids\": [ids from the tools], \"rationale\": string, \"swaps\": []}. "
    "On a later pass, swaps should name the premium dishes you are dropping. "
    "Do not invent prices or portion counts. The desk scales portions and costs."
)

PRICING_SYSTEM = (
    "You write one client-facing sentence for a Mesa Clara quotation. "
    "Call read_quote first. Use only the numbers that tool returns. "
    "Reply with JSON {\"summary\": string}. Do not invent a different total."
)


def intake_tools():
    def submit_event(arguments: dict) -> dict:
        try:
            event = EventRequest.model_validate(arguments or {})
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        missing = missing_fields(event)
        return {
            "ok": True,
            "event": event.model_dump(mode="json"),
            "missing": missing,
            "questions": questions_for(missing),
        }

    submit_event.tool_description = (
        "File the event fields you extracted. Omit any field the text did not state."
    )
    submit_event.tool_schema = {
        "type": "object",
        "properties": {
            "client_name": {"type": "string"},
            "event_name": {"type": "string"},
            "event_type": {"type": "string", "enum": ["corporate", "debut", "wedding", "fiesta"]},
            "guests": {"type": "integer"},
            "event_date": {"type": "string", "description": "YYYY-MM-DD"},
            "event_time": {"type": "string", "description": "HH:MM"},
            "venue": {"type": "string"},
            "city": {"type": "string"},
            "budget_php": {"type": "number"},
            "exclude": {"type": "array", "items": {"type": "string"}},
            "vegetarian_guests": {"type": "integer"},
        },
    }
    return {"submit_event": submit_event}


def parse_with_model(model, text: str):
    parsed, records, review = run_agent(
        agent="intake",
        model=model,
        tools=intake_tools(),
        schema=IntakeNote,
        user=text,
        system=INTAKE_SYSTEM,
    )
    event = None
    for record in records:
        if record["name"] == "submit_event" and record["result"].get("ok"):
            event = EventRequest.model_validate(record["result"]["event"])
    follow = parsed.follow_up if parsed else ""
    if not follow and event is not None:
        follow = " ".join(questions_for(missing_fields(event)))
    return event, follow, records, review, parsed.note if parsed else ""


def menu_tools(catalog: dict, index, event: dict):
    recipes, ingredients, _ = _index(catalog)

    def search_recipes(arguments: dict) -> dict:
        query = str(arguments.get("query") or event.get("event_type") or "")
        hits = index.search(query, k=4) if index is not None else []
        tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        ranked = []
        for recipe in recipes.values():
            if not _diet_ok(recipe, list(event.get("exclude") or [])):
                continue
            blob = f"{recipe['name']} {recipe['slot']} {' '.join(recipe['proteins'])}".lower()
            score = len(tokens.intersection(blob.split()))
            ranked.append((score, recipe))
        ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
        candidates = []
        for _score, recipe in ranked[:12]:
            candidates.append(
                {
                    "id": recipe["id"],
                    "name": recipe["name"],
                    "slot": recipe["slot"],
                    "premium": recipe["premium"],
                    "book_cost_per_guest_php": pesos(_book_cost(recipe, ingredients)),
                }
            )
        return {"hits": hits, "candidates": candidates}

    def check_diet(arguments: dict) -> dict:
        exclude = arguments.get("exclude") or event.get("exclude") or []
        ids = arguments.get("recipe_ids") or ([arguments["recipe_id"]] if arguments.get("recipe_id") else [])
        rows = []
        for recipe_id in ids:
            recipe = recipes.get(recipe_id)
            if recipe is None:
                rows.append({"id": recipe_id, "ok": False, "reason": "unknown dish"})
                continue
            ok = _diet_ok(recipe, list(exclude))
            rows.append({"id": recipe_id, "ok": ok, "reason": "allowed" if ok else "excluded by the brief"})
        return {"results": rows}

    def get_budget_per_head(arguments: dict) -> dict:
        budget = float(arguments.get("budget_php") if arguments.get("budget_php") is not None else event["budget_php"])
        guests = int(arguments.get("guests") if arguments.get("guests") is not None else event["guests"])
        if guests <= 0:
            return {"ok": False, "error": "guests must be positive"}
        return {"ok": True, "guests": guests, "budget_php": budget, "per_head_php": float(pesos(D(str(budget)) / D(guests)))}

    search_recipes.tool_description = "Search the kitchen binder and list diet-safe dishes with book cost per guest."
    search_recipes.tool_schema = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }
    check_diet.tool_description = "Check dish ids against the brief's excluded proteins. Does not change the menu."
    check_diet.tool_schema = {
        "type": "object",
        "properties": {
            "recipe_ids": {"type": "array", "items": {"type": "string"}},
            "exclude": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["recipe_ids"],
    }
    get_budget_per_head.tool_description = "Divide the client budget by the guest count. Does not set the quote."
    get_budget_per_head.tool_schema = {
        "type": "object",
        "properties": {"budget_php": {"type": "number"}, "guests": {"type": "integer"}},
        "required": ["budget_php", "guests"],
    }
    return {
        "search_recipes": search_recipes,
        "check_diet": check_diet,
        "get_budget_per_head": get_budget_per_head,
    }


def choose_with_model(model, catalog, index, event: dict, revision: int, avoid: list[str]):
    user = json.dumps(
        {
            "event_type": event.get("event_type"),
            "guests": event.get("guests"),
            "budget_php": event.get("budget_php"),
            "exclude": event.get("exclude") or [],
            "vegetarian_guests": event.get("vegetarian_guests") or 0,
            "revision": revision,
            "avoid": avoid,
            "city": event.get("city"),
        }
    )
    choice, records, review = run_agent(
        agent="menu",
        model=model,
        tools=menu_tools(catalog, index, event),
        schema=MenuChoice,
        user=user,
        system=MENU_SYSTEM,
    )
    return choice, records, review


def pricing_tools(priced: dict, guests: int):
    def read_quote(_arguments: dict) -> dict:
        return {
            "ok": True,
            "guests": guests,
            "quote_php": priced["quote_php"],
            "budget_php": priced["budget_php"],
            "gap_php": priced["gap_php"],
            "food_php": priced["food_php"],
            "service_php": priced["service_php"],
            "status": priced["status"],
            "guidance": priced["guidance"],
        }

    read_quote.tool_description = "Read the quote the cost engine already computed. Do not change it."
    read_quote.tool_schema = {"type": "object", "properties": {}}
    return {"read_quote": read_quote}


def summarize_with_model(model, priced: dict, guests: int):
    summary, records, review = run_agent(
        agent="pricing",
        model=model,
        tools=pricing_tools(priced, guests),
        schema=QuoteSummary,
        user="Write the client sentence from read_quote.",
        system=PRICING_SYSTEM,
    )
    text = summary.summary if summary else ""
    if text and not _numbers_allowed(text, priced, guests):
        review = True
        text = ""
    return text, records, review


def _numbers_allowed(text: str, priced: dict, guests: int) -> bool:
    allowed = [
        float(priced["quote_php"]),
        float(priced["budget_php"]),
        abs(float(priced["gap_php"])),
        float(priced["food_php"]),
        float(priced["purchase_php"]),
        float(priced["service_php"]),
        float(priced["equipment_php"]),
        float(priced["travel_php"]),
        float(priced["overhead_php"]),
        float(guests),
    ]
    if priced["quote_php"] and guests:
        allowed.append(round(float(priced["quote_php"]) / guests, 2))
    for raw in re.findall(r"\d[\d,]*\.?\d*", text):
        value = float(raw.replace(",", ""))
        if not any(abs(value - item) < 0.05 for item in allowed):
            return False
    return True
