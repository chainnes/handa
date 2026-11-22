from decimal import Decimal

from handa.engine.ops import net_shortfall


def test_shortfall_is_need_minus_stock():
    assert net_shortfall("10", "4") == Decimal("6.00")
    assert net_shortfall(Decimal("2.5"), Decimal("2.5")) == Decimal("0")


def test_stock_above_need_orders_nothing():
    assert net_shortfall("3", "5") == Decimal("0")


def test_fractional_need_rounds_to_the_centavo_of_quantity():
    assert net_shortfall("1.005", "0") == Decimal("1.01")
