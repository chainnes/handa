from decimal import Decimal

from handa.engine.money import D, pesos, q
from handa.engine.ops import quote_parts


def test_quote_formula_for_a_quezon_city_buffet():
    food = D("1000")
    parts = quote_parts(food, 60, "buffet", "corporate", "Quezon City")
    service = q(D("160") * 60)
    equipment = D("3800")
    overhead = q((food + service + equipment) * D("0.10"))
    cost = q(food + service + equipment + overhead)
    quote = q(cost / D("0.74"))
    assert parts["travel"] == 0
    assert parts["service"] == service
    assert parts["cost"] == cost
    assert parts["quote"] == quote
    assert pesos(parts["quote"]) == float(quote)


def test_travel_is_added_outside_quezon_city():
    parts = quote_parts(D("1000"), 60, "buffet", "corporate", "Taguig")
    assert parts["travel"] == Decimal("900")
