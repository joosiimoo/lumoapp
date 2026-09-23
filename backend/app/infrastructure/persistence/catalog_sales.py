from __future__ import annotations

from datetime import datetime
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
from app.domain.sales import (
    InputUnit,
    Payment,
    PaymentMethod,
    PaymentSource,
    PaymentStatus,
    SaleItem,
    SaleItemSource,
    SaleSession,
    SaleSessionStatus,
)
from app.domain.shared.errors import ProductNotFoundError, SaleNotOpenError, TenantScopeViolationError, ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import PaymentRow, ProductAliasRow, ProductRow, SaleItemRow, SaleSessionRow
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
        return self.get_active_session(tenant=tenant, conversation_id=conversation_id, for_update=False)

    def get_active_session(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        for_update: bool = False,
    ) -> SaleSession | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = select(SaleSessionRow).where(
            SaleSessionRow.business_id == tenant.business_id,
            SaleSessionRow.actor_id == tenant.actor_id,
            SaleSessionRow.status.in_(
                (SaleSessionStatus.OPEN.value, SaleSessionStatus.READY_TO_CHARGE.value)
            ),
        )
        if conversation_id:
            stmt = stmt.where(SaleSessionRow.conversation_id == conversation_id)
        else:
            stmt = stmt.where(SaleSessionRow.conversation_id.is_(None))
        if for_update:
            stmt = stmt.with_for_update()
        row = self._session.scalar(stmt)
        return _to_session(row) if row is not None else None

    def update_session_status(
        self,
        *,
        tenant: TenantContext,
        sale_session_id: UUID,
        status: SaleSessionStatus,
    ) -> SaleSession:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.get(SaleSessionRow, sale_session_id)
        if row is None or row.business_id != tenant.business_id:
            raise ValidationAppError("sale session not found")
        row.status = status.value
        self._session.flush()
        return _to_session(row)

    def confirm_session(
        self,
        *,
        tenant: TenantContext,
        sale_session_id: UUID,
        operational_day_id: UUID,
        confirmed_at: datetime,
    ) -> SaleSession:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.get(SaleSessionRow, sale_session_id)
        if row is None or row.business_id != tenant.business_id:
            raise ValidationAppError("sale session not found")
        row.status = SaleSessionStatus.CONFIRMED.value
        row.operational_day_id = operational_day_id
        row.confirmed_at = confirmed_at
        self._session.flush()
        return _to_session(row)

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
        session_row = self._session.get(SaleSessionRow, item.sale_session_id)
        if session_row is None or session_row.business_id != tenant.business_id:
            raise TenantScopeViolationError("sale session not found")
        if session_row.status != SaleSessionStatus.OPEN.value:
            raise SaleNotOpenError("sale is not open")
        row = SaleItemRow(
            id=item.id,
            business_id=tenant.business_id,
            sale_session_id=item.sale_session_id,
            product_id=item.product_id,
            source_type=item.source_type.value,
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
            select(SaleItemRow)
            .where(
                SaleItemRow.business_id == tenant.business_id,
                SaleItemRow.sale_session_id == sale_session_id,
            )
            .order_by(SaleItemRow.created_at.asc(), SaleItemRow.id.asc())
        ).all()
        return [_to_item(row) for row in rows]

    def add_payment(self, *, tenant: TenantContext, payment: Payment) -> Payment:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        session_row = self._session.get(SaleSessionRow, payment.sale_session_id)
        if session_row is None or session_row.business_id != tenant.business_id:
            raise TenantScopeViolationError("sale session not found")
        if payment.business_id != tenant.business_id:
            raise TenantScopeViolationError("payment tenant does not match sale session")
        row = PaymentRow(
            id=payment.id,
            business_id=tenant.business_id,
            sale_session_id=payment.sale_session_id,
            actor_id=tenant.actor_id,
            method=payment.method.value,
            amount=payment.amount.amount,
            currency=payment.amount.currency,
            status=PaymentStatus.RECORDED.value,
            source=PaymentSource.MANUAL_CAPTURE.value,
        )
        self._session.add(row)
        self._session.flush()
        return _to_payment(row)

    def get_payment_for_session(self, *, tenant: TenantContext, sale_session_id: UUID) -> Payment | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(PaymentRow).where(
                PaymentRow.business_id == tenant.business_id,
                PaymentRow.sale_session_id == sale_session_id,
            )
        )
        return _to_payment(row) if row is not None else None

    def get_latest_confirmed_session(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
    ) -> SaleSession | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = select(SaleSessionRow).where(
            SaleSessionRow.business_id == tenant.business_id,
            SaleSessionRow.actor_id == tenant.actor_id,
            SaleSessionRow.status == SaleSessionStatus.CONFIRMED.value,
        )
        if conversation_id:
            stmt = stmt.where(SaleSessionRow.conversation_id == conversation_id)
        else:
            stmt = stmt.where(SaleSessionRow.conversation_id.is_(None))
        stmt = stmt.order_by(SaleSessionRow.created_at.desc(), SaleSessionRow.id.desc())
        row = self._session.scalar(stmt)
        return _to_session(row) if row is not None else None

    def get_session_by_id(
        self,
        *,
        tenant: TenantContext,
        sale_session_id: UUID,
        for_update: bool = False,
    ) -> SaleSession | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = select(SaleSessionRow).where(
            SaleSessionRow.id == sale_session_id,
            SaleSessionRow.business_id == tenant.business_id,
            SaleSessionRow.actor_id == tenant.actor_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        row = self._session.scalar(stmt)
        return _to_session(row) if row is not None else None

    def has_newer_active_session(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        created_at: datetime | None,
        session_id: UUID,
    ) -> bool:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = select(SaleSessionRow.id).where(
            SaleSessionRow.business_id == tenant.business_id,
            SaleSessionRow.actor_id == tenant.actor_id,
            SaleSessionRow.status.in_(
                (SaleSessionStatus.OPEN.value, SaleSessionStatus.READY_TO_CHARGE.value)
            ),
            SaleSessionRow.id != session_id,
        )
        if conversation_id:
            stmt = stmt.where(SaleSessionRow.conversation_id == conversation_id)
        else:
            stmt = stmt.where(SaleSessionRow.conversation_id.is_(None))
        if created_at is not None:
            stmt = stmt.where(
                (SaleSessionRow.created_at > created_at)
                | ((SaleSessionRow.created_at == created_at) & (SaleSessionRow.id > session_id))
            )
        return self._session.scalar(stmt) is not None

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
        operational_day_id=row.operational_day_id,
        confirmed_at=row.confirmed_at,
    )


def _to_item(row: SaleItemRow) -> SaleItem:
    return SaleItem(
        id=row.id,
        business_id=row.business_id,
        sale_session_id=row.sale_session_id,
        product_id=row.product_id,
        source_type=SaleItemSource(row.source_type),
        product_name_snapshot=row.product_name_snapshot,
        quantity_input=Decimal(row.quantity_input),
        unit_input=InputUnit(row.unit_input),
        quantity_normalized=Decimal(row.quantity_normalized),
        unit_normalized=SaleUnit(row.unit_normalized),
        unit_price=Money(row.unit_price, row.currency),
        line_total=Money(row.line_total, row.currency),
    )


def _to_payment(row: PaymentRow) -> Payment:
    return Payment(
        id=row.id,
        business_id=row.business_id,
        sale_session_id=row.sale_session_id,
        actor_id=row.actor_id,
        method=PaymentMethod(row.method),
        amount=Money(row.amount, row.currency),
        status=PaymentStatus(row.status),
        source=PaymentSource(row.source),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
