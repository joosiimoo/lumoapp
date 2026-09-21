from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum

from app.domain.catalog.product import SaleUnit
from app.domain.shared.errors import UnitNotSupportedError, ValidationAppError
from app.domain.shared.money import Money


class InputUnit(StrEnum):
    GRAM = "gram"
    KILOGRAM = "kilogram"
    UNIT = "unit"
    PACKAGE = "package"


def parse_quantity(value: str) -> Decimal:
    if isinstance(value, float):  # type: ignore[unreachable]
        raise TypeError("quantity must not use float")
    try:
        quantity = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValidationAppError("quantity must be a positive decimal") from exc
    if quantity <= 0:
        raise ValidationAppError("quantity must be greater than zero")
    return quantity


def normalize_quantity(quantity: Decimal, unit: InputUnit, sale_unit: SaleUnit) -> tuple[Decimal, SaleUnit]:
    if unit is InputUnit.GRAM:
        if sale_unit is not SaleUnit.KILOGRAM:
            raise UnitNotSupportedError("grams are only valid for kilogram products")
        return quantity / Decimal("1000"), SaleUnit.KILOGRAM
    if unit is InputUnit.KILOGRAM and sale_unit is SaleUnit.KILOGRAM:
        return quantity, SaleUnit.KILOGRAM
    if unit is InputUnit.UNIT and sale_unit is SaleUnit.UNIT:
        return quantity, SaleUnit.UNIT
    if unit is InputUnit.PACKAGE and sale_unit is SaleUnit.PACKAGE:
        return quantity, SaleUnit.PACKAGE
    raise UnitNotSupportedError(
        "unit is not compatible with the product sale unit",
        details={"unit": unit, "sale_unit": sale_unit},
    )


def format_normalized_quantity(quantity: Decimal, unit: SaleUnit) -> str:
    if unit is SaleUnit.KILOGRAM:
        quantized = quantity.quantize(Decimal("0.001"))
        return f"{quantized:.3f}"
    return format(quantity, "f")


def calculate_line_total(quantity_normalized: Decimal, unit_price: Money) -> Money:
    return unit_price.times(quantity_normalized)
