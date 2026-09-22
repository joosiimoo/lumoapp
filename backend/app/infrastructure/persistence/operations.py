from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.operations import DaySummaryTotals, OperationalDay, OperationalDayStatus
from app.domain.sales import PaymentStatus, SaleSessionStatus
from app.domain.shared.errors import TenantScopeViolationError, ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import OperationalDayRow, PaymentRow, SaleSessionRow
from app.infrastructure.persistence.rls import set_current_business_id


class OperationsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def ensure_open_day(
        self,
        *,
        tenant: TenantContext,
        business_date: date,
        timezone_name: str,
        day_id: UUID,
        opened_at: datetime,
    ) -> tuple[OperationalDay, bool]:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        stmt = (
            insert(OperationalDayRow)
            .values(
                id=day_id,
                business_id=tenant.business_id,
                business_date=business_date,
                status=OperationalDayStatus.OPEN.value,
                timezone=timezone_name,
                created_at=opened_at,
                updated_at=opened_at,
            )
            .on_conflict_do_nothing(constraint="uq_operational_days_business_date")
            .returning(OperationalDayRow.id)
        )
        inserted_id = self._session.execute(stmt).scalar_one_or_none()
        if inserted_id is not None:
            row = self._session.get(OperationalDayRow, inserted_id)
            assert row is not None
            return _to_day(row), True
        existing = self._session.scalar(
            select(OperationalDayRow).where(
                OperationalDayRow.business_id == tenant.business_id,
                OperationalDayRow.business_date == business_date,
            )
        )
        if existing is None:
            raise ValidationAppError("operational day could not be ensured")
        return _to_day(existing), False

    def get_by_date(self, *, tenant: TenantContext, business_date: date) -> OperationalDay | None:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        row = self._session.scalar(
            select(OperationalDayRow).where(
                OperationalDayRow.business_id == tenant.business_id,
                OperationalDayRow.business_date == business_date,
            )
        )
        return _to_day(row) if row is not None else None

    def summarize_day(
        self,
        *,
        tenant: TenantContext,
        operational_day_id: UUID,
        currency: str,
    ) -> DaySummaryTotals:
        tenant = _require_tenant(tenant)
        set_current_business_id(self._session, tenant.business_id)
        currencies = self._session.scalars(
            select(PaymentRow.currency)
            .join(SaleSessionRow, SaleSessionRow.id == PaymentRow.sale_session_id)
            .where(
                SaleSessionRow.business_id == tenant.business_id,
                SaleSessionRow.operational_day_id == operational_day_id,
                SaleSessionRow.status == SaleSessionStatus.CONFIRMED.value,
                PaymentRow.status == PaymentStatus.RECORDED.value,
            )
            .distinct()
        ).all()
        if any(code != currency for code in currencies):
            raise ValidationAppError("payment currency does not match the business")
        cash = func.coalesce(func.sum(PaymentRow.amount).filter(PaymentRow.method == "cash"), 0)
        card = func.coalesce(func.sum(PaymentRow.amount).filter(PaymentRow.method == "card"), 0)
        transfer = func.coalesce(func.sum(PaymentRow.amount).filter(PaymentRow.method == "transfer"), 0)
        row = self._session.execute(
            select(
                func.count(func.distinct(SaleSessionRow.id)),
                func.coalesce(func.sum(PaymentRow.amount), 0),
                cash,
                card,
                transfer,
            )
            .select_from(SaleSessionRow)
            .join(PaymentRow, PaymentRow.sale_session_id == SaleSessionRow.id)
            .where(
                SaleSessionRow.business_id == tenant.business_id,
                SaleSessionRow.operational_day_id == operational_day_id,
                SaleSessionRow.status == SaleSessionStatus.CONFIRMED.value,
                PaymentRow.business_id == tenant.business_id,
                PaymentRow.status == PaymentStatus.RECORDED.value,
            )
        ).one()
        return DaySummaryTotals(
            sale_count=int(row[0] or 0),
            gross_sales_total=_money(row[1], currency),
            cash_total=_money(row[2], currency),
            card_total=_money(row[3], currency),
            transfer_total=_money(row[4], currency),
            currency=currency,
        )


def _money(amount: Decimal | int | str, currency: str) -> str:
    if isinstance(amount, float):
        raise TypeError("money amounts must not use float")
    if not isinstance(amount, (Decimal, str)):
        amount = Decimal(str(amount))
    return Money(amount, currency).to_json()["amount"]


def _to_day(row: OperationalDayRow) -> OperationalDay:
    return OperationalDay(
        id=row.id,
        business_id=row.business_id,
        business_date=row.business_date,
        status=OperationalDayStatus(row.status),
        timezone=row.timezone,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_tenant(tenant: TenantContext) -> TenantContext:
    if tenant is None:  # type: ignore[truthy-bool]
        raise ValidationAppError("tenant is required")
    if tenant.business_id is None:
        raise TenantScopeViolationError("business is required")
    return tenant
