from decimal import Decimal

import pytest

from handa.engine.ops import ingredient_need, scale_portions


def test_rice_and_drinks_get_a_five_percent_buffer():
    assert scale_portions(60, "rice") == 63
    assert scale_portions(60, "drink") == 63
    assert scale_portions(40, "rice") == 42
    assert scale_portions(1, "drink") == 2


def test_other_courses_are_one_per_guest():
    assert scale_portions(60, "viand") == 60
    assert scale_portions(120, "dessert") == 120


def test_ingredient_need_scales_with_portions():
    assert ingredient_need("0.12", 10) == Decimal("1.20")
    assert ingredient_need(Decimal("0.005"), 63) == Decimal("0.32")


def test_negative_guests_are_rejected():
    with pytest.raises(ValueError):
        scale_portions(-1, "rice")
