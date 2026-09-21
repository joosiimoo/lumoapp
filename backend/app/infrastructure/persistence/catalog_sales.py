from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.catalog import (
    PricingType,
    Product,
    ProductAlias,
    ProductStatus,
    SaleUnit,
    resolve_products,
)
from app.domain.sales import InputUnit, SaleItem, SaleSession, SaleSessionStatus
from app.domain.shared.errors import ProductNotFoundError, TenantScopeViolationError, ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import ProductAliasRow, ProductRow, SaleItemRow, SaleSessionRow
from app.infrastructure.persistence.rls import set_current_business_id


def _require_tenant(tenant: TenantContext | None) -> TenantContext:
    if tenant is None:
        raise ValidationAppError("tenant is required")
    return tenant


def _to_product(row: ProductRow) -> Product:
    return Product(
        id=row.id,
        business_id=row.business_id,
        name=row.name,
        normalized_name=row.normalized_name,
        sale_unit=SaleUnit(row.sale_unit),
        pricing_type=PricingType(row.pricing_type),
        current_price=Money(row.current_price, "MXN"),
        status=ProductStatus(row.status),
    )


class CatalogRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def resolve(self, *, tenant: TenantContext, query: str):
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        products = [
            _to_product(row)
            for row in self._session.scalars(
                select(ProductRow).where(ProductRow.business_id == tenant.business_id)
            ).all()
        ]
        aliases = [
            ProductAlias(product_id=row.product_id, normalized_alias=row.normalized_alias)
            for row in self._session.scalars(
                select(ProductAliasRow).where(ProductAliasRow.business_id == tenant.business_id)
            ).all()
        ]
        return resolve_products(query, products, aliases)

    def get(self, *, tenant: TenantContext, product_id: UUID) -> Product:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.get(ProductRow, product_id)
        if row is None or row.business_id != tenant.business_id:
            raise ProductNotFoundError("product not found")
        return _to_product(row)

    def add(self, *, tenant: TenantContext, product: Product) -> Product:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = ProductRow(
            id=product.id,
            business_id=tenant.business_id,
            name=product.name,
            normalized_name=product.normalized_name,
            sale_unit=product.sale_unit.value,
            pricing_type=product.pricing_type.value,
            current_price=product.current_price.amount,
            status=product.status.value,
        )
        self._session.add(row)
        self._session.flush()
        return _to_product(row)

    def add_alias(self, *, tenant: TenantContext, product_id: UUID, alias: str, normalized_alias: str) -> None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        self._session.add(
            ProductAliasRow(
                business_id=tenant.business_id,
                product_id=product_id,
                alias=alias,
                normalized_alias=normalized_alias,
            )
        )
        self._session.flush()


class SalesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_open_session(self, *, tenant: TenantContext, conversation_id: str | None) -> SaleSession | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = select(SaleSessionRow).where(
            SaleSessionRow.business_id == tenant.business_id,
            SaleSessionRow.actor_id == tenant.actor_id,
            SaleSessionRow.status == SaleSessionStatus.OPEN.value,
        )
        if conversation_id:
            stmt = stmt.where(SaleSessionRow.conversation_id == conversation_id)
        else:
            stmt = stmt.where(SaleSessionRow.conversation_id.is_(None))
        row = self._session.scalar(stmt)
        return _to_session(row) if row is not None else None

    def add_session(self, *, tenant: TenantContext, session: SaleSession) -> SaleSession:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = SaleSessionRow(
            id=session.id,
            business_id=tenant.business_id,
            actor_id=tenant.actor_id,
            conversation_id=session.conversation_id,
            status=session.status.value,
            currency=session.currency,
        )
        self._session.add(row)
        self._session.flush()
        return _to_session(row)

    def add_item(self, *, tenant: TenantContext, item: SaleItem) -> SaleItem:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = SaleItemRow(
            id=item.id,
            business_id=tenant.business_id,
            sale_session_id=item.sale_session_id,
            product_id=item.product_id,
            product_name_snapshot=item.product_name_snapshot,
            quantity_input=item.quantity_input,
            unit_input=item.unit_input.value,
            quantity_normalized=item.quantity_normalized,
            unit_normalized=item.unit_normalized.value,
            unit_price=item.unit_price.amount,
            currency=item.unit_price.currency,
            line_total=item.line_total.amount,
        )
        self._session.add(row)
        self._session.flush()
        return _to_item(row)

    def list_items(self, *, tenant: TenantContext, sale_session_id: UUID) -> list[SaleItem]:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        rows = self._session.scalars(
            select(SaleItemRow).where(
                SaleItemRow.business_id == tenant.business_id,
                SaleItemRow.sale_session_id == sale_session_id,
            )
        ).all()
        return [_to_item(row) for row in rows]

    def count_sessions(self, *, tenant: TenantContext) -> int:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        rows = self._session.scalars(
            select(SaleSessionRow).where(SaleSessionRow.business_id == tenant.business_id)
        ).all()
        return len(rows)


def _to_session(row: SaleSessionRow) -> SaleSession:
    return SaleSession(
        id=row.id,
        business_id=row.business_id,
        actor_id=row.actor_id,
        conversation_id=row.conversation_id,
        status=SaleSessionStatus(row.status),
        currency=row.currency,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _to_item(row: SaleItemRow) -> SaleItem:
    return SaleItem(
        id=row.id,
        business_id=row.business_id,
        sale_session_id=row.sale_session_id,
        product_id=row.product_id,
        product_name_snapshot=row.product_name_snapshot,
        quantity_input=Decimal(row.quantity_input),
        unit_input=InputUnit(row.unit_input),
        quantity_normalized=Decimal(row.quantity_normalized),
        unit_normalized=SaleUnit(row.unit_normalized),
        unit_price=Money(row.unit_price, row.currency),
        line_total=Money(row.line_total, row.currency),
    )
