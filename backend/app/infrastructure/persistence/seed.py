from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import issue_dev_token
from app.domain.catalog import PricingType, Product, ProductStatus, SaleUnit, normalize_product_name
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.catalog_sales import CatalogRepository
from app.infrastructure.persistence.models import BusinessRow, MembershipRow, ProductAliasRow, ProductRow, UserRow
from app.infrastructure.persistence.rls import set_current_business_id

CARROTA_NAME = "Carrota"
ZANAHORIA_NAME = "Zanahoria"
TOMATE_NAME = "Tomate"
GALLETA_A_NAME = "Galleta A"
ZANAHORIA_PRICE = Decimal("25.00")
TOMATE_PRICE = Decimal("20.00")
GALLETA_A_PRICE = Decimal("12.00")
CARROTA_BUSINESS_ID = UUID("01900000-0000-7000-8000-000000000001")
CARROTA_OWNER_ID = UUID("01900000-0000-7000-8000-000000000002")
ZANAHORIA_PRODUCT_ID = UUID("01900000-0000-7000-8000-000000000003")
TOMATE_PRODUCT_ID = UUID("01900000-0000-7000-8000-000000000004")
GALLETA_A_PRODUCT_ID = UUID("01900000-0000-7000-8000-000000000005")


def ensure_carrota_seed(session: Session, *, token_secret: str | None = None) -> tuple[TenantContext, str | None]:
    tenant = TenantContext(business_id=CARROTA_BUSINESS_ID, actor_id=CARROTA_OWNER_ID)
    set_current_business_id(session, CARROTA_BUSINESS_ID)
    business = session.get(BusinessRow, CARROTA_BUSINESS_ID)
    if business is None:
        session.add(
            BusinessRow(
                id=CARROTA_BUSINESS_ID,
                name=CARROTA_NAME,
                currency="MXN",
                timezone="America/Mexico_City",
                locale="es-MX",
            )
        )
        session.flush()
    user = session.get(UserRow, CARROTA_OWNER_ID)
    if user is None:
        session.add(UserRow(id=CARROTA_OWNER_ID, business_id=CARROTA_BUSINESS_ID, name="Carrota owner"))
        session.flush()
    membership = session.scalar(
        select(MembershipRow).where(
            MembershipRow.business_id == CARROTA_BUSINESS_ID,
            MembershipRow.user_id == CARROTA_OWNER_ID,
        )
    )
    if membership is None:
        session.add(MembershipRow(business_id=CARROTA_BUSINESS_ID, user_id=CARROTA_OWNER_ID, role="owner"))
        session.flush()
    product = session.get(ProductRow, ZANAHORIA_PRODUCT_ID)
    if product is None:
        CatalogRepository(session).add(
            tenant=tenant,
            product=Product(
                id=ZANAHORIA_PRODUCT_ID,
                business_id=CARROTA_BUSINESS_ID,
                name=ZANAHORIA_NAME,
                normalized_name=normalize_product_name(ZANAHORIA_NAME),
                sale_unit=SaleUnit.KILOGRAM,
                pricing_type=PricingType.PER_KILOGRAM,
                current_price=Money(ZANAHORIA_PRICE, "MXN"),
                status=ProductStatus.ACTIVE,
            ),
        )
        session.flush()
    catalog = CatalogRepository(session)
    tomate = session.get(ProductRow, TOMATE_PRODUCT_ID)
    if tomate is None:
        catalog.add(
            tenant=tenant,
            product=Product(
                id=TOMATE_PRODUCT_ID,
                business_id=CARROTA_BUSINESS_ID,
                name=TOMATE_NAME,
                normalized_name=normalize_product_name(TOMATE_NAME),
                sale_unit=SaleUnit.KILOGRAM,
                pricing_type=PricingType.PER_KILOGRAM,
                current_price=Money(TOMATE_PRICE, "MXN"),
                status=ProductStatus.ACTIVE,
            ),
        )
        session.flush()
    galleta = session.get(ProductRow, GALLETA_A_PRODUCT_ID)
    if galleta is None:
        catalog.add(
            tenant=tenant,
            product=Product(
                id=GALLETA_A_PRODUCT_ID,
                business_id=CARROTA_BUSINESS_ID,
                name=GALLETA_A_NAME,
                normalized_name=normalize_product_name(GALLETA_A_NAME),
                sale_unit=SaleUnit.UNIT,
                pricing_type=PricingType.PER_UNIT,
                current_price=Money(GALLETA_A_PRICE, "MXN"),
                status=ProductStatus.ACTIVE,
            ),
        )
        session.flush()
    alias = session.scalar(
        select(ProductAliasRow).where(
            ProductAliasRow.business_id == CARROTA_BUSINESS_ID,
            ProductAliasRow.product_id == GALLETA_A_PRODUCT_ID,
            ProductAliasRow.normalized_alias == "galletas a",
        )
    )
    if alias is None:
        catalog.add_alias(
            tenant=tenant,
            product_id=GALLETA_A_PRODUCT_ID,
            alias="galletas a",
            normalized_alias=normalize_product_name("galletas a"),
        )
        session.flush()
    token = None
    if token_secret:
        token = issue_dev_token(user_id=CARROTA_OWNER_ID, business_id=CARROTA_BUSINESS_ID, secret=token_secret)
    return tenant, token
