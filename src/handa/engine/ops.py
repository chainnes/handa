"""Deterministic catering math. Agents may talk. They do not invent quantities, pesos, or times."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_CEILING
import re

from handa.engine.money import D, pesos, q

BUFFERED_SLOTS = {"rice", "drink"}
SERVICE_PER_HEAD = {"dropoff": D("55"), "buffet": D("160"), "plated": D("380")}
SERVICE_DOWN = {"plated": "buffet", "buffet": "dropoff", "dropoff": "dropoff"}
DEFAULT_SERVICE = {"corporate": "buffet", "debut": "buffet", "wedding": "plated", "fiesta": "buffet"}
FLOOR_MARGIN = {"corporate": D("0.26"), "debut": D("0.28"), "wedding": D("0.32"), "fiesta": D("0.24")}
OVERHEAD = D("0.10")
TRAVEL = D("900")
EQUIPMENT = {"dropoff": D("1200"), "buffet": D("3800"), "plated": D("9000")}

SIGNATURE = {
    "corporate": ["garlic_rice", "chicken_afritada", "chopsuey", "buko_pandan", "iced_tea"],
    "debut": ["java_rice", "lechon_belly", "beef_kaldereta", "lumpiang_sariwa", "buko_salad", "calamansi_juice"],
    "wedding": ["garlic_rice", "beef_kaldereta", "grilled_tanigue", "chopsuey", "leche_flan", "calamansi_juice"],
    "fiesta": ["java_rice", "chicken_inasal", "pancit", "chopsuey", "buko_pandan", "iced_tea"],
}
HOUSE_SWAP = {
    "lechon_belly": "chicken_inasal",
    "beef_kaldereta": "chicken_afritada",
    "beef_steak": "chicken_afritada",
    "grilled_tanigue": "fish_sarciado",
    "buko_salad": "buko_pandan",
    "calamansi_juice": "iced_tea",
    "leche_flan": "buko_pandan",
    "pork_sisig": "chicken_inasal",
}
DIET_SWAP = {
    "pork": {"lechon_belly": "chicken_inasal", "pork_menudo": "chicken_afritada", "pork_sisig": "chicken_inasal", "pork_adobo": "chicken_adobo", "spaghetti": "pancit"},
    "beef": {"beef_kaldereta": "chicken_afritada", "beef_steak": "chicken_bbq", "beef_nilaga": "chicken_adobo"},
    "seafood": {"fish_sarciado": "chicken_afritada", "grilled_tanigue": "chicken_inasal", "fish_ginataan": "tofu_curry", "fish_paksiw": "tofu_adobo"},
}


def scale_portions(guests: int, slot: str) -> int:
    """Rice and drinks get a 5% buffer, rounded up. Everything else is one per guest."""
    if guests < 0:
        raise ValueError("guests cannot be negative")
    if slot not in BUFFERED_SLOTS:
        return guests
    raw = D(guests) * D("1.05")
    return int(raw.to_integral_value(rounding=ROUND_CEILING))


def ingredient_need(qty_per_guest: Decimal | str | float, portions: int) -> Decimal:
    return q(D(str(qty_per_guest)) * D(portions))


def net_shortfall(need: Decimal | str | float, on_hand: Decimal | str | float) -> Decimal:
    """Buy only what the kitchen does not already hold."""
    gap = D(str(need)) - D(str(on_hand))
    if gap <= 0:
        return D(0)
    return q(gap)


def order_quantity(shortfall: Decimal | str | float, moq: Decimal | str | float) -> Decimal:
    """A zero shortfall orders nothing. Any positive shortfall is raised to the minimum order."""
    gap = D(str(shortfall))
    if gap <= 0:
        return D(0)
    minimum = D(str(moq))
    return q(gap if gap >= minimum else minimum)


def lead_days(supplier: dict, overrides: dict | None = None) -> int:
    extra = int((overrides or {}).get(supplier["id"], 0))
    return int(supplier["lead_days"]) + extra


def choose_supplier(offers: list[dict], suppliers: dict[str, dict], days_until: int, overrides: dict | None = None) -> dict:
    """Cheapest offer that can arrive in time. If the cheapest is late, switch."""
    if not offers:
        return {"ok": False, "reason": "no offer", "switched_from": None}
    ranked = sorted(offers, key=lambda offer: (D(str(offer["price"])), offer["supplier_id"]))
    cheapest = ranked[0]
    for offer in ranked:
        supplier = suppliers[offer["supplier_id"]]
        if lead_days(supplier, overrides) <= days_until:
            switched = offer["supplier_id"] != cheapest["supplier_id"]
            return {
                "ok": True,
                "offer": offer,
                "supplier": supplier,
                "lead_days": lead_days(supplier, overrides),
                "switched_from": cheapest["supplier_id"] if switched else None,
                "reason": "lead time" if switched else "cheapest",
            }
    supplier = suppliers[cheapest["supplier_id"]]
    return {
        "ok": False,
        "offer": cheapest,
        "supplier": supplier,
        "lead_days": lead_days(supplier, overrides),
        "switched_from": None,
        "reason": "no supplier can meet the lead time",
    }


def backward_schedule(event_date: date, event_time: str, *, guests: int, has_lechon: bool, max_lead_days: int) -> list[dict]:
    """Tasks are placed by walking backward from service, then shown in time order."""
    hour, minute = (int(part) for part in event_time.split(":"))
    service = datetime.combine(event_date, time(hour, minute))
    prep_hours = 8 if guests >= 100 else 6
    points = [
        ("Market order deadline", service - timedelta(days=max(max_lead_days, 0), hours=8)),
        ("Prep starts", service - timedelta(hours=prep_hours)),
        ("Load the van", service - timedelta(hours=3)),
        ("On site", service - timedelta(hours=1)),
        ("Service", service),
        ("Pack down", service + timedelta(hours=3)),
    ]
    if has_lechon:
        points.append(("Confirm lechon delivery", service - timedelta(days=1, hours=6)))
    points.sort(key=lambda item: item[1])
    return [
        {"task": label, "at": moment.isoformat(timespec="minutes"), "hours_before_service": round((service - moment).total_seconds() / 3600, 2)}
        for label, moment in points
    ]


def outside_qc(city: str) -> bool:
    tokens = set(re.sub(r"[^a-z]+", " ", city.lower()).split())
    if "quezon" in tokens and "city" in tokens:
        return False
    if tokens == {"qc"} or "qc" in tokens:
        return False
    return True


def service_style(event_type: str, revision: int) -> str:
    base = DEFAULT_SERVICE[event_type]
    style = base
    if revision >= 2:
        style = SERVICE_DOWN[base]
    return style


def _index(catalog: dict) -> tuple[dict, dict, dict]:
    recipes = {recipe["id"]: recipe for recipe in catalog["recipes"]}
    ingredients = {item["id"]: item for item in catalog["ingredients"]}
    suppliers = {supplier["id"]: supplier for supplier in catalog["suppliers"]}
    return recipes, ingredients, suppliers


def _diet_ok(recipe: dict, exclude: list[str]) -> bool:
    proteins = set(recipe["proteins"])
    if "pork" in exclude and "pork" in proteins:
        return False
    if "beef" in exclude and "beef" in proteins:
        return False
    if "seafood" in exclude and "seafood" in proteins:
        return False
    return True


def _uses(recipe: dict, avoid: set[str]) -> bool:
    return any(item["id"] in avoid for item in recipe["ingredients"] if D(str(item["qty"])) > 0)


def resolve_menu_ids(event: dict, revision: int, catalog: dict, avoid: list[str] | None = None) -> list[str]:
    recipes, _, _ = _index(catalog)
    avoid_set = set(avoid or [])
    exclude = list(event.get("exclude") or [])
    chosen: list[str] = []
    seen: set[str] = set()
    for recipe_id in SIGNATURE[event["event_type"]]:
        current = recipe_id
        if revision >= 1 and current in HOUSE_SWAP:
            current = HOUSE_SWAP[current]
        for rule in exclude:
            current = DIET_SWAP.get(rule, {}).get(current, current)
        guard = 0
        while guard < 6 and (not _diet_ok(recipes[current], exclude) or _uses(recipes[current], avoid_set) or current in seen):
            current = HOUSE_SWAP.get(current, "tofu_adobo" if current != "tofu_adobo" else "chopsuey")
            guard += 1
        if current in seen or not _diet_ok(recipes[current], exclude):
            continue
        seen.add(current)
        chosen.append(current)
    return chosen


def build_menu(
    event: dict,
    revision: int,
    catalog: dict,
    avoid: list[str] | None = None,
    citations: list | None = None,
    recipe_ids: list[str] | None = None,
) -> dict:
    recipes, ingredients, _ = _index(catalog)
    guests = int(event["guests"])
    veg = int(event.get("vegetarian_guests") or 0)
    meat_guests = max(0, guests - veg)
    style = service_style(event["event_type"], revision)
    lines = []
    warnings = []
    if revision >= 1:
        warnings.append(f"Cost-down pass {revision}: premium dishes swapped for house dishes.")
    if revision >= 2:
        warnings.append(f"Service dropped to {style}.")
    chosen = recipe_ids if recipe_ids else resolve_menu_ids(event, revision, catalog, avoid)
    for recipe_id in chosen:
        recipe = recipes.get(recipe_id)
        if recipe is None:
            warnings.append(f"Ignored unknown dish id {recipe_id}.")
            continue
        audience = "all"
        if any(protein in recipe["proteins"] for protein in ("pork", "beef", "seafood", "chicken")):
            portions = meat_guests
            audience = "meat"
        else:
            portions = scale_portions(guests, recipe["slot"])
        if portions <= 0:
            continue
        book = _book_cost(recipe, ingredients)
        lines.append(
            {
                "recipe_id": recipe_id,
                "name": recipe["name"],
                "slot": recipe["slot"],
                "portions": portions,
                "audience": audience,
                "diet": recipe["diet"],
                "allergens": recipe["allergens"],
                "unit_cost_php": pesos(book),
                "line_cost_php": pesos(q(book * D(portions))),
            }
        )
    if veg > 0 and not any(line["recipe_id"] == "tofu_adobo" for line in lines):
        recipe = recipes["tofu_adobo"]
        book = _book_cost(recipe, ingredients)
        lines.append(
            {
                "recipe_id": "tofu_adobo",
                "name": recipe["name"],
                "slot": recipe["slot"],
                "portions": veg,
                "audience": "vegetarian",
                "diet": recipe["diet"],
                "allergens": recipe["allergens"],
                "unit_cost_php": pesos(book),
                "line_cost_php": pesos(q(book * D(veg))),
            }
        )
    food = q(sum((D(str(line["line_cost_php"])) for line in lines), D(0)))
    return {
        "service_style": style,
        "revision": revision,
        "lines": lines,
        "food_cost_php": pesos(food),
        "warnings": warnings,
        "citations": citations or [],
    }


def _book_cost(recipe: dict, ingredients: dict) -> Decimal:
    total = D(0)
    for item in recipe["ingredients"]:
        if item["id"] not in ingredients:
            continue
        price = D(str(ingredients[item["id"]]["offers"][0]["price"]))
        total += D(str(item["qty"])) * price
    return q(total)


def build_inventory(menu: dict, catalog: dict, on_hand_overrides: dict | None = None) -> dict:
    """Roll the menu into ingredient needs and net them against what is already in the kitchen."""
    recipes, ingredients, _ = _index(catalog)
    overrides = on_hand_overrides or {}
    needs: dict[str, Decimal] = {}
    for line in menu["lines"]:
        recipe = recipes[line["recipe_id"]]
        for item in recipe["ingredients"]:
            if item["id"] not in ingredients:
                continue
            needs[item["id"]] = needs.get(item["id"], D(0)) + D(str(item["qty"])) * D(line["portions"])
    rows = []
    for iid, need in sorted(needs.items()):
        spec = ingredients[iid]
        held = D(str(overrides[iid])) if iid in overrides else D(str(spec["on_hand"]))
        if held < 0:
            held = D(0)
        shortfall = net_shortfall(q(need), held)
        rows.append(
            {
                "ingredient_id": iid,
                "name": spec["name"],
                "unit": spec["unit"],
                "need": pesos(q(need)) if q(need) == q(need) else float(q(need)),
                "on_hand": float(q(held)),
                "shortfall": float(shortfall),
                "perishable": spec["perishable"],
            }
        )
    # pesos() returns float; keep shortfall exact via the float of a quantized decimal.
    for row in rows:
        row["need"] = float(q(D(str(row["need"]))))
    return {"lines": rows}


def build_procurement(inventory: dict, event: dict, catalog: dict, overrides: dict | None = None, today: date | None = None) -> dict:
    _, ingredients, suppliers = _index(catalog)
    today = today or date.today()
    event_date = date.fromisoformat(event["event_date"])
    days_until = (event_date - today).days
    lines = []
    alternatives = []
    purchase = D(0)
    for row in inventory["lines"]:
        shortfall = D(str(row["shortfall"]))
        spec = ingredients[row["ingredient_id"]]
        if shortfall <= 0:
            lines.append({**row, "order_qty": 0, "supplier_id": None, "supplier_name": "Kitchen stock", "unit_price_php": 0, "line_cost_php": 0, "moq": 0, "lead_days": 0, "switched_from": None, "infeasible": False, "note": "Covered by stock."})
            continue
        choice = choose_supplier(spec["offers"], suppliers, days_until, overrides)
        if not choice["ok"]:
            alternatives.append(
                f"No supplier can deliver {spec['name']} in {days_until} day(s). Move the date past {choice['lead_days']} day(s), or drop dishes that use it."
            )
            lines.append(
                {
                    **row,
                    "order_qty": float(shortfall),
                    "supplier_id": None,
                    "supplier_name": "None",
                    "unit_price_php": float(choice["offer"]["price"]),
                    "line_cost_php": 0,
                    "moq": float(choice["offer"]["moq"]),
                    "lead_days": int(choice["lead_days"]),
                    "switched_from": None,
                    "infeasible": True,
                    "note": choice["reason"],
                }
            )
            continue
        offer = choice["offer"]
        qty = order_quantity(shortfall, offer["moq"])
        cost = q(qty * D(str(offer["price"])))
        purchase += cost
        switched = choice["switched_from"]
        note = "Minimum order applied." if qty > shortfall else "Ordered the shortfall."
        if switched:
            note = f"Switched from {suppliers[switched]['name']} ({choice['reason']}). " + note
        lines.append(
            {
                **row,
                "order_qty": float(qty),
                "supplier_id": offer["supplier_id"],
                "supplier_name": choice["supplier"]["name"],
                "unit_price_php": float(offer["price"]),
                "line_cost_php": pesos(cost),
                "moq": float(offer["moq"]),
                "lead_days": int(choice["lead_days"]),
                "switched_from": switched,
                "infeasible": False,
                "note": note,
            }
        )
    return {
        "lines": lines,
        "purchase_php": pesos(purchase),
        "infeasible": bool(alternatives),
        "alternatives": alternatives,
        "days_until": days_until,
    }


def build_logistics(menu: dict, procurement: dict, event: dict) -> dict:
    guests = int(event["guests"])
    style = menu["service_style"]
    has_lechon = any(line["recipe_id"] == "lechon_belly" for line in menu["lines"])
    ordered_leads = [int(line.get("lead_days") or 0) for line in procurement["lines"] if line.get("order_qty", 0) > 0]
    max_lead = max(ordered_leads or [0])
    timeline = backward_schedule(
        date.fromisoformat(event["event_date"]),
        event["event_time"],
        guests=guests,
        has_lechon=has_lechon,
        max_lead_days=max(1, max_lead),
    )
    if style == "dropoff":
        cooks, servers = max(1, (guests + 49) // 50), 0
    elif style == "buffet":
        cooks, servers = max(1, (guests + 39) // 40), max(1, (guests + 24) // 25)
    else:
        cooks, servers = max(1, (guests + 29) // 30), max(1, (guests + 14) // 15)
    crew = [{"role": "Cook", "count": cooks}]
    if servers:
        crew.append({"role": "Server", "count": servers})
    if guests >= 50 and style != "dropoff":
        crew.append({"role": "Captain", "count": 1})
    if outside_qc(event["city"]):
        crew.append({"role": "Driver", "count": 1})
    return {"crew": crew, "timeline": timeline, "service_style": style, "warnings": list(procurement.get("alternatives") or [])}


def build_pricing(menu: dict, procurement: dict, event: dict, revision: int, max_revisions: int) -> dict:
    guests = int(event["guests"])
    style = menu["service_style"]
    food = D(str(menu["food_cost_php"]))
    # Food on the quote is the book cost of portions. Cash out is the purchase list.
    purchase = D(str(procurement["purchase_php"]))
    service = q(SERVICE_PER_HEAD[style] * D(guests))
    equipment = EQUIPMENT[style]
    travel = TRAVEL if outside_qc(event["city"]) else D(0)
    overhead = q((food + service + equipment + travel) * OVERHEAD)
    cost = q(food + service + equipment + travel + overhead)
    floor = FLOOR_MARGIN[event["event_type"]]
    quote = q(cost / (D(1) - floor))
    budget = D(str(event["budget_php"]))
    gap = q(quote - budget)
    if procurement.get("infeasible"):
        status = "infeasible"
        guidance = "A supplier cannot make the date. Alternatives are on the file."
    elif gap <= 0:
        status = "pass"
        guidance = "The quote fits the budget."
    elif revision < max_revisions:
        status = "revise"
        guidance = f"Over by ₱{pesos(gap):,.2f}. Another cost-down pass is allowed."
    else:
        status = "over_budget"
        guidance = f"Still ₱{pesos(gap):,.2f} over after {revision} cost-down pass(es)."
    return {
        "food_php": pesos(food),
        "purchase_php": pesos(purchase),
        "service_php": pesos(service),
        "equipment_php": pesos(equipment),
        "travel_php": pesos(travel),
        "overhead_php": pesos(overhead),
        "cost_php": pesos(cost),
        "quote_php": pesos(quote),
        "budget_php": pesos(budget),
        "gap_php": pesos(gap),
        "margin_rate": float(floor),
        "status": status,
        "guidance": guidance,
        "currency": "PHP",
        "currency_note": "Synthetic pesos.",
    }


def quote_parts(food: Decimal, guests: int, style: str, event_type: str, city: str) -> dict:
    """Public cost formula used by tests and by build_pricing."""
    service = q(SERVICE_PER_HEAD[style] * D(guests))
    equipment = EQUIPMENT[style]
    travel = TRAVEL if outside_qc(city) else D(0)
    overhead = q((food + service + equipment + travel) * OVERHEAD)
    cost = q(food + service + equipment + travel + overhead)
    floor = FLOOR_MARGIN[event_type]
    quote = q(cost / (D(1) - floor))
    return {"service": service, "equipment": equipment, "travel": travel, "overhead": overhead, "cost": cost, "quote": quote, "floor": floor}
