from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from app.domain.catalog import (
    PricingType,
    Product,
    ProductAlias,
    ProductMatch,
    ProductStatus,
    SaleUnit,
    normalize_product_name,
    require_valid_pairing,
    resolve_products,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.money import Money
import pytest


def _product(*, name: str, status: ProductStatus = ProductStatus.ACTIVE) -> Product:
    return Product(
        id=uuid4(),
        business_id=uuid4(),
        name=name,
        normalized_name=normalize_product_name(name),
        sale_unit=SaleUnit.KILOGRAM,
        pricing_type=PricingType.PER_KILOGRAM,
        current_price=Money(Decimal("25.00"), "MXN"),
        status=status,
    )


def test_normalize_strips_accents_and_case() -> None:
    assert normalize_product_name("  ZANAHORÍA  ") == "zanahoria"


def test_unique_accent_insensitive_match() -> None:
    zanahoria = _product(name="Zanahoria")
    result = resolve_products("ZANAHORÍA", [zanahoria])
    assert result.match is ProductMatch.UNIQUE
    assert result.product is zanahoria


def test_inactive_product_is_excluded() -> None:
    inactive = _product(name="Zanahoria", status=ProductStatus.INACTIVE)
    result = resolve_products("zanahoria", [inactive])
    assert result.match is ProductMatch.NONE
    assert result.product is None


def test_ambiguous_alias_match() -> None:
    first = _product(name="Zanahoria criolla")
    second = _product(name="Zanahoria baby")
    aliases = [
        ProductAlias(product_id=first.id, normalized_alias="zanahoria"),
        ProductAlias(product_id=second.id, normalized_alias="zanahoria"),
    ]
    result = resolve_products("zanahoria", [first, second], aliases)
    assert result.match is ProductMatch.AMBIGUOUS
    assert result.product is None
    assert len(result.candidates) == 2


def test_invalid_pairing_rejected() -> None:
    with pytest.raises(ValidationAppError):
        require_valid_pairing(SaleUnit.KILOGRAM, PricingType.PER_UNIT)


def _count_product(*, name: str) -> Product:
    return Product(
        id=uuid4(),
        business_id=uuid4(),
        name=name,
        normalized_name=normalize_product_name(name),
        sale_unit=SaleUnit.UNIT,
        pricing_type=PricingType.PER_UNIT,
        current_price=Money(Decimal("12.00"), "MXN"),
        status=ProductStatus.ACTIVE,
    )


def test_galleta_alias_resolves_uniquely() -> None:
    galleta = _count_product(name="Galleta A")
    aliases = [ProductAlias(product_id=galleta.id, normalized_alias="galletas a")]
    by_name = resolve_products("galleta a", [galleta], aliases)
    by_alias = resolve_products("galletas a", [galleta], aliases)
    papa = resolve_products("papa", [galleta], aliases)
    assert by_name.match is ProductMatch.UNIQUE
    assert by_alias.match is ProductMatch.UNIQUE
    assert by_alias.product is galleta
    assert papa.match is ProductMatch.NONE
