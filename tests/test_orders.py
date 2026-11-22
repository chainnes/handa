from decimal import Decimal

from handa.engine.ops import choose_supplier, order_quantity


def test_zero_shortfall_ignores_the_minimum():
    assert order_quantity("0", "5") == Decimal("0")


def test_shortfall_below_the_minimum_is_raised():
    assert order_quantity("2", "5") == Decimal("5")


def test_shortfall_above_the_minimum_is_kept():
    assert order_quantity("8", "5") == Decimal("8.00")


def test_a_late_cheap_supplier_is_switched():
    suppliers = {
        "slow": {"id": "slow", "name": "Slow", "lead_days": 3},
        "fast": {"id": "fast", "name": "Fast", "lead_days": 0},
    }
    offers = [
        {"supplier_id": "slow", "price": 10, "moq": 1},
        {"supplier_id": "fast", "price": 14, "moq": 2},
    ]
    choice = choose_supplier(offers, suppliers, days_until=0)
    assert choice["ok"] is True
    assert choice["supplier"]["id"] == "fast"
    assert choice["switched_from"] == "slow"


def test_no_supplier_is_an_explicit_miss():
    suppliers = {"slow": {"id": "slow", "name": "Slow", "lead_days": 3}}
    offers = [{"supplier_id": "slow", "price": 10, "moq": 1}]
    choice = choose_supplier(offers, suppliers, days_until=1)
    assert choice["ok"] is False
    assert "lead time" in choice["reason"]
