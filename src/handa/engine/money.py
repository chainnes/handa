"""Centavo-safe helpers. The engine stays in Decimal until a schema needs JSON."""

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def D(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(value)


def pesos(value: Decimal) -> float:
    return float(value.quantize(CENT, rounding=ROUND_HALF_UP))


def q(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
