from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.catalog.product import SaleUnit
from app.domain.sales.quantity import (
    InputUnit,
    calculate_line_total,
    format_normalized_quantity,
    normalize_quantity,
    parse_quantity,
)
from app.domain.shared.errors import UnitNotSupportedError, ValidationAppError
from app.domain.shared.money import Money


def test_900_grams_becomes_0_900_kg_and_22_50() -> None:
    quantity = parse_quantity("900")
    normalized, unit = normalize_quantity(quantity, InputUnit.GRAM, SaleUnit.KILOGRAM)
    assert format_normalized_quantity(normalized, unit) == "0.900"
    total = calculate_line_total(normalized, Money(Decimal("25.00"), "MXN"))
    assert total.to_json() == {"amount": "22.50", "currency": "MXN"}


def test_zero_quantity_rejected() -> None:
    with pytest.raises(ValidationAppError):
        parse_quantity("0")


def test_gram_on_unit_product_rejected() -> None:
    with pytest.raises(UnitNotSupportedError):
        normalize_quantity(Decimal("900"), InputUnit.GRAM, SaleUnit.UNIT)


def test_line_total_rejects_float() -> None:
    with pytest.raises(TypeError, match="float"):
        Money(Decimal("25.00"), "MXN").times(0.9)  # type: ignore[arg-type]
