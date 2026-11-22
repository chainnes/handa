"""Fixed-seed synthetic kitchen. Same seed, same book. Prices are teaching pesos, not a quote.

Run `python -m handa.sample_data.generate` to write catalog.json.
"""

from __future__ import annotations

import json
from pathlib import Path

SEED = 20261115

SUPPLIERS = [
    {"id": "balintawak", "name": "Balintawak Wet Market", "lead_days": 1},
    {"id": "nova", "name": "Nova Wholesale QC", "lead_days": 1},
    {"id": "mila", "name": "Mila's Lechon, Quezon City", "lead_days": 2},
    {"id": "antipolo", "name": "Antipolo Farm Gate", "lead_days": 2},
    {"id": "pacific", "name": "Pacific Cold Storage", "lead_days": 3},
    {"id": "dry", "name": "Mesa Clara Dry Store", "lead_days": 0},
]


def _ingredient(iid, name, unit, on_hand, perishable, offers):
    return {
        "id": iid,
        "name": name,
        "unit": unit,
        "on_hand": on_hand,
        "perishable": perishable,
        "offers": [{"supplier_id": s, "price": p, "moq": m} for s, p, m in offers],
    }


def _recipe(iid, name, slot, proteins, premium, items, allergens=None):
    diet = ["vegetarian"] if proteins in (["vegetarian"], ["vegan"]) or proteins == [] else list(proteins)
    if proteins == ["vegan"]:
        diet = ["vegetarian", "vegan"]
    return {
        "id": iid,
        "name": name,
        "slot": slot,
        "proteins": proteins,
        "diet": diet,
        "premium": premium,
        "allergens": allergens or [],
        "ingredients": [{"id": i, "qty": q} for i, q in items],
    }


def generate_catalog() -> dict:
    """Return the synthetic book. Seed is recorded so a rerun can be checked."""
    ingredients = [
        _ingredient("rice", "Well-milled rice", "kg", 4, False, [("nova", 50, 5), ("dry", 58, 2)]),
        _ingredient("garlic", "Garlic", "kg", 0.3, True, [("antipolo", 280, 1), ("balintawak", 300, 0.2), ("dry", 360, 0.2)]),
        _ingredient("oil", "Cooking oil", "L", 1, False, [("nova", 100, 1), ("dry", 110, 0.5)]),
        _ingredient("chicken", "Chicken", "kg", 1.5, True, [("balintawak", 240, 1), ("dry", 290, 2)]),
        _ingredient("pork", "Pork shoulder", "kg", 0, True, [("balintawak", 280, 1)]),
        _ingredient("lechon", "Lechon belly, cooked", "portion", 0, True, [("mila", 210, 10)]),
        _ingredient("beef", "Beef chuck", "kg", 0, True, [("pacific", 470, 3), ("balintawak", 520, 1)]),
        _ingredient("fish", "Fish fillet", "kg", 0, True, [("pacific", 220, 2), ("balintawak", 260, 0.5)]),
        _ingredient("tofu", "Firm tofu", "kg", 1, True, [("nova", 100, 1), ("dry", 120, 1)]),
        _ingredient("vegetables", "Mixed vegetables", "kg", 2, True, [("antipolo", 36, 2), ("balintawak", 40, 1), ("dry", 55, 1)]),
        _ingredient("cream", "All-purpose cream", "L", 0, False, [("nova", 250, 0.5), ("dry", 270, 1)]),
        _ingredient("sugar", "Sugar", "kg", 1, False, [("nova", 50, 1), ("dry", 55, 1)]),
        _ingredient("noodles", "Noodles", "kg", 0.5, False, [("nova", 100, 1), ("dry", 115, 1)]),
        _ingredient("seasoning", "Seasoning kit", "pack", 20, False, [("dry", 3, 1), ("nova", 3, 5)]),
        _ingredient("calamansi", "Calamansi", "kg", 0, True, [("antipolo", 150, 1), ("balintawak", 160, 0.5), ("dry", 200, 0.5)]),
        _ingredient("buko", "Buko meat", "kg", 0, True, [("antipolo", 110, 2), ("balintawak", 120, 1), ("dry", 160, 1)]),
        _ingredient("milk", "Condensed milk", "L", 0, False, [("nova", 180, 1), ("dry", 190, 1)]),
        _ingredient("egg", "Egg", "pc", 12, True, [("nova", 8, 30), ("balintawak", 9, 6), ("dry", 12, 6)]),
    ]
    seasoning = ("seasoning", 1)
    recipes = [
        _recipe("garlic_rice", "Garlic rice", "rice", ["vegan"], False, [("rice", 0.08), ("garlic", 0.005), ("oil", 0.01), seasoning]),
        _recipe("java_rice", "Java rice", "rice", ["vegan"], False, [("rice", 0.08), ("oil", 0.01), ("garlic", 0.004), seasoning]),
        _recipe("plain_rice", "Plain rice", "rice", ["vegan"], False, [("rice", 0.08), seasoning]),
        _recipe("fried_rice", "Fried rice", "rice", ["vegetarian"], False, [("rice", 0.08), ("egg", 0.3), ("oil", 0.01), ("garlic", 0.004)]),
        _recipe("chicken_afritada", "Chicken afritada", "viand", ["chicken"], False, [("chicken", 0.12), ("vegetables", 0.06), ("oil", 0.008), seasoning]),
        _recipe("chicken_inasal", "Chicken inasal", "viand", ["chicken"], False, [("chicken", 0.14), ("calamansi", 0.01), ("garlic", 0.004), seasoning]),
        _recipe("chicken_adobo", "Chicken adobo", "viand", ["chicken"], False, [("chicken", 0.13), ("garlic", 0.005), ("oil", 0.008), seasoning]),
        _recipe("chicken_curry", "Chicken curry", "viand", ["chicken"], False, [("chicken", 0.12), ("vegetables", 0.05), ("cream", 0.02), seasoning]),
        _recipe("chicken_bbq", "Chicken barbecue", "viand", ["chicken"], False, [("chicken", 0.14), ("sugar", 0.01), ("calamansi", 0.008), seasoning]),
        _recipe("lechon_belly", "Lechon belly", "centerpiece", ["pork"], True, [("lechon", 1)]),
        _recipe("pork_menudo", "Pork menudo", "viand", ["pork"], False, [("pork", 0.1), ("vegetables", 0.05), ("oil", 0.008), seasoning]),
        _recipe("pork_sisig", "Pork sisig", "viand", ["pork"], True, [("pork", 0.12), ("calamansi", 0.01), ("garlic", 0.004), seasoning]),
        _recipe("pork_adobo", "Pork adobo", "viand", ["pork"], False, [("pork", 0.11), ("garlic", 0.005), ("oil", 0.008), seasoning]),
        _recipe("beef_kaldereta", "Beef kaldereta", "viand", ["beef"], True, [("beef", 0.12), ("vegetables", 0.05), ("cream", 0.015), seasoning]),
        _recipe("beef_steak", "Beef steak", "viand", ["beef"], True, [("beef", 0.13), ("calamansi", 0.01), ("oil", 0.008), seasoning]),
        _recipe("beef_nilaga", "Beef nilaga", "viand", ["beef"], False, [("beef", 0.11), ("vegetables", 0.08), seasoning]),
        _recipe("fish_sarciado", "Fish sarciado", "viand", ["seafood"], False, [("fish", 0.12), ("egg", 0.4), ("vegetables", 0.04), seasoning], ["fish"]),
        _recipe("grilled_tanigue", "Grilled tanigue", "viand", ["seafood"], True, [("fish", 0.16), ("calamansi", 0.012), ("garlic", 0.004), seasoning], ["fish"]),
        _recipe("fish_ginataan", "Fish ginataan", "viand", ["seafood"], False, [("fish", 0.12), ("vegetables", 0.06), ("cream", 0.02), seasoning], ["fish"]),
        _recipe("fish_paksiw", "Fish paksiw", "viand", ["seafood"], False, [("fish", 0.12), ("garlic", 0.004), ("vegetables", 0.04), seasoning], ["fish"]),
        _recipe("tofu_adobo", "Tofu adobo", "viand", ["vegetarian"], False, [("tofu", 0.12), ("garlic", 0.004), ("oil", 0.008), seasoning], ["soy"]),
        _recipe("tofu_curry", "Tofu curry", "viand", ["vegetarian"], False, [("tofu", 0.12), ("vegetables", 0.05), ("cream", 0.02), seasoning], ["soy"]),
        _recipe("lumpiang_sariwa", "Lumpiang sariwa", "vegetable", ["vegetarian"], False, [("vegetables", 0.08), ("tofu", 0.04), ("garlic", 0.003), seasoning], ["soy"]),
        _recipe("chopsuey", "Chopsuey", "vegetable", ["vegetarian"], False, [("vegetables", 0.1), ("tofu", 0.03), ("oil", 0.006), seasoning]),
        _recipe("pinakbet", "Pinakbet", "vegetable", ["vegetarian"], False, [("vegetables", 0.12), ("garlic", 0.003), seasoning]),
        _recipe("ensalada", "Ensalada", "vegetable", ["vegan"], False, [("vegetables", 0.08), ("calamansi", 0.008)]),
        _recipe("ginataang_kalabasa", "Ginataang kalabasa", "vegetable", ["vegetarian"], False, [("vegetables", 0.1), ("cream", 0.02), seasoning]),
        _recipe("gising_gising", "Gising-gising", "vegetable", ["vegetarian"], False, [("vegetables", 0.08), ("cream", 0.02), ("garlic", 0.003), seasoning]),
        _recipe("pancit", "Pancit guisado", "noodle", ["vegetarian"], False, [("noodles", 0.08), ("vegetables", 0.05), ("tofu", 0.03), ("oil", 0.006), seasoning], ["gluten"]),
        _recipe("bihon", "Bihon", "noodle", ["vegetarian"], False, [("noodles", 0.07), ("vegetables", 0.05), ("oil", 0.006), seasoning], ["gluten"]),
        _recipe("sotanghon", "Sotanghon", "noodle", ["vegetarian"], False, [("noodles", 0.07), ("vegetables", 0.04), ("chicken", 0.03), seasoning], ["gluten"]),
        _recipe("spaghetti", "Filipino spaghetti", "noodle", ["pork"], False, [("noodles", 0.08), ("pork", 0.04), ("sugar", 0.01), seasoning], ["gluten"]),
        _recipe("buko_pandan", "Buko pandan", "dessert", ["vegetarian"], False, [("buko", 0.04), ("milk", 0.02), ("cream", 0.015), ("sugar", 0.01)], ["dairy"]),
        _recipe("buko_salad", "Buko salad", "dessert", ["vegetarian"], True, [("buko", 0.05), ("milk", 0.03), ("cream", 0.03), ("sugar", 0.01)], ["dairy"]),
        _recipe("leche_flan", "Leche flan", "dessert", ["vegetarian"], False, [("milk", 0.04), ("egg", 1), ("sugar", 0.02)], ["dairy", "egg"]),
        _recipe("fruit_platter", "Fruit platter", "dessert", ["vegan"], False, [("vegetables", 0.06), ("sugar", 0.005)]),
        _recipe("mais_con_yelo", "Mais con yelo", "dessert", ["vegetarian"], False, [("milk", 0.03), ("sugar", 0.02), ("cream", 0.01)], ["dairy"]),
        _recipe("turon", "Turon", "dessert", ["vegan"], False, [("vegetables", 0.05), ("sugar", 0.015), ("oil", 0.008)]),
        _recipe("iced_tea", "Iced tea", "drink", ["vegan"], False, [("sugar", 0.015), ("seasoning", 0.2)]),
        _recipe("calamansi_juice", "Calamansi juice", "drink", ["vegan"], True, [("calamansi", 0.03), ("sugar", 0.02)]),
    ]
    # The sisig line above was built with a conditional that still yields 3 items. Guard the count.
    assert len(recipes) == 40, len(recipes)
    assert len(SUPPLIERS) == 6
    requests = [
        {
            "id": "town-hall",
            "label": "Town hall",
            "blurb": "Complete brief. No pork. Fits on the first pass.",
            "text": "Northwind BPO needs a corporate lunch for 60 guests in 21 days at 12:00 in Taguig at One Park Avenue. Budget 45000 pesos. No pork. 8 vegetarian guests.",
        },
        {
            "id": "debut-ask",
            "label": "Debut, no budget",
            "blurb": "Missing the budget. The desk stops and asks.",
            "text": "The Reyes family wants a debut for 120 guests in Antipolo in 30 days at 18:00 at the garden hall. 12 vegetarian guests.",
        },
        {
            "id": "wedding",
            "label": "Tagaytay wedding",
            "blurb": "Plated wedding with room in the budget.",
            "text": "Santos and Dela Cruz want a wedding for 180 guests in Tagaytay in 45 days at 17:00 at the ridge terrace. Budget 450000 pesos. 15 vegetarian guests.",
        },
        {
            "id": "same-day",
            "label": "Same-day lunch",
            "blurb": "Today. The wet market is already too slow, so buying switches supplier.",
            "text": "Habagat Studio needs a corporate lunch for 40 guests today at 12:30 in Quezon City at Examiner Street. Budget 40000 pesos. No pork.",
        },
        {
            "id": "too-small",
            "label": "Budget that cannot close",
            "blurb": "Two cost-down passes still miss. Flagged over budget.",
            "text": "The San Roque committee wants a debut for 120 guests in Quezon City in 14 days at 11:00 at the covered court. Budget 30000 pesos.",
        },
        {
            "id": "fiesta-ask",
            "label": "Fiesta, no headcount",
            "blurb": "Missing the guest count. The desk asks before it prices.",
            "text": "Please price a fiesta in Quezon City in 20 days at 11:00 at the barangay court. Budget 70000 pesos.",
        },
    ]
    assert len(requests) == 6
    return {
        "seed": SEED,
        "currency": "PHP",
        "currency_note": "Synthetic teaching prices for a fictional Quezon City caterer. Not a live quote.",
        "suppliers": SUPPLIERS,
        "ingredients": ingredients,
        "recipes": recipes,
        "requests": requests,
    }


def main() -> None:
    catalog = generate_catalog()
    path = Path(__file__).resolve().parent / "catalog.json"
    path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"wrote {path} seed={catalog['seed']} recipes={len(catalog['recipes'])}")


if __name__ == "__main__":
    main()
