from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.domain.shared.errors import ValidationAppError
from app.domain.shared.money import Money


class SaleUnit(StrEnum):
    UNIT = "unit"
    PACKAGE = "package"
    KILOGRAM = "kilogram"


class PricingType(StrEnum):
    PER_UNIT = "per_unit"
    PER_PACKAGE = "per_package"
    PER_KILOGRAM = "per_kilogram"


class ProductStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


_VALID_PAIRS = {
    (SaleUnit.UNIT, PricingType.PER_UNIT),
    (SaleUnit.PACKAGE, PricingType.PER_PACKAGE),
    (SaleUnit.KILOGRAM, PricingType.PER_KILOGRAM),
}


def require_valid_pairing(sale_unit: SaleUnit, pricing_type: PricingType) -> None:
    if (sale_unit, pricing_type) not in _VALID_PAIRS:
        raise ValidationAppError(
            "sale_unit and pricing_type are incompatible",
            details={"sale_unit": sale_unit, "pricing_type": pricing_type},
        )


@dataclass(frozen=True, slots=True)
class Product:
    id: UUID
    business_id: UUID
    name: str
    normalized_name: str
    sale_unit: SaleUnit
    pricing_type: PricingType
    current_price: Money
    status: ProductStatus

    @property
    def is_active(self) -> bool:
        return self.status is ProductStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class ProductAlias:
    product_id: UUID
    normalized_alias: str
