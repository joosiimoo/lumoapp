"""Test-owned tenants. Cleanup may target only businesses this process created."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import issue_dev_token
from app.domain.catalog import PricingType, Product, ProductStatus, SaleUnit, normalize_product_name
from app.domain.shared.ids import new_uuid7
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.catalog_sales import CatalogRepository
from app.infrastructure.persistence.models import BusinessRow, MembershipRow, ProductRow, UserRow
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import (
    CARROTA_BUSINESS_ID,
    GALLETA_A_NAME,
    GALLETA_A_PRICE,
    TOMATE_NAME,
    TOMATE_PRICE,
    ZANAHORIA_NAME,
    ZANAHORIA_PRICE,
)

PILOT_BUSINESS_IDS = frozenset({CARROTA_BUSINESS_ID})
TEST_BUSINESS_NAME = "Lumo Test Business"
_TEST_TENANTS: set[UUID] = set()


def register_test_tenant(business_id: UUID) -> None:
    if business_id in PILOT_BUSINESS_IDS:
        raise RuntimeError("refusing to treat a pilot tenant as test-owned")
    _TEST_TENANTS.add(business_id)


def catalog_product_id(session: Session, business_id: UUID, name: str) -> UUID:
    set_current_business_id(session, business_id)
    product_id = session.scalar(
        select(ProductRow.id).where(ProductRow.business_id == business_id, ProductRow.name == name)
    )
    if product_id is None:
        raise RuntimeError(f"test catalog has no product named {name}")
    return product_id


def require_test_tenant(business_id: UUID) -> None:
    if business_id in PILOT_BUSINESS_IDS or business_id not in _TEST_TENANTS:
        raise RuntimeError("cleanup refused: target is not a test-owned tenant")


def seed_catalog_tenant(
    session: Session,
    *,
    name: str = TEST_BUSINESS_NAME,
    business_id: UUID | None = None,
) -> tuple[TenantContext, str]:
    """A new merchant with the catalog names the sale tests speak. Not a pilot tenant."""
    from tests.conftest import TEST_SECRET

    business_id = new_uuid7() if business_id is None else business_id
    user_id = new_uuid7()
    register_test_tenant(business_id)
    set_current_business_id(session, business_id)
    session.add(
        BusinessRow(
            id=business_id,
            name=name,
            currency="MXN",
            timezone="America/Mexico_City",
            locale="es-MX",
        )
    )
    session.flush()
    session.add(UserRow(id=user_id, business_id=business_id, name=f"{name} owner"))
    session.flush()
    session.add(MembershipRow(business_id=business_id, user_id=user_id, role="owner"))
    session.flush()
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    catalog = CatalogRepository(session)
    products = (
        (ZANAHORIA_NAME, SaleUnit.KILOGRAM, PricingType.PER_KILOGRAM, ZANAHORIA_PRICE),
        (TOMATE_NAME, SaleUnit.KILOGRAM, PricingType.PER_KILOGRAM, TOMATE_PRICE),
        (GALLETA_A_NAME, SaleUnit.UNIT, PricingType.PER_UNIT, GALLETA_A_PRICE),
    )
    galleta_id: UUID | None = None
    for product_name, unit, pricing, price in products:
        product_id = new_uuid7()
        if product_name == GALLETA_A_NAME:
            galleta_id = product_id
        catalog.add(
            tenant=tenant,
            product=Product(
                id=product_id,
                business_id=business_id,
                name=product_name,
                normalized_name=normalize_product_name(product_name),
                sale_unit=unit,
                pricing_type=pricing,
                current_price=Money(Decimal(price), "MXN"),
                status=ProductStatus.ACTIVE,
            ),
        )
    session.flush()
    assert galleta_id is not None
    catalog.add_alias(
        tenant=tenant,
        product_id=galleta_id,
        alias="galletas a",
        normalized_alias=normalize_product_name("galletas a"),
    )
    session.commit()
    token = issue_dev_token(user_id=user_id, business_id=business_id, secret=TEST_SECRET)
    return tenant, token
