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
from app.infrastructure.persistence.models import BusinessRow, MembershipRow, ProductRow, UserRow
from app.infrastructure.persistence.rls import set_current_business_id

CARROTA_NAME = "Carrota"
ZANAHORIA_NAME = "Zanahoria"
ZANAHORIA_PRICE = Decimal("25.00")
CARROTA_BUSINESS_ID = UUID("01900000-0000-7000-8000-000000000001")
CARROTA_OWNER_ID = UUID("01900000-0000-7000-8000-000000000002")
ZANAHORIA_PRODUCT_ID = UUID("01900000-0000-7000-8000-000000000003")


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
    token = None
    if token_secret:
        token = issue_dev_token(user_id=CARROTA_OWNER_ID, business_id=CARROTA_BUSINESS_ID, secret=token_secret)
    return tenant, token
