"""One-statement read of one OperationalDay's confirmed sale lines."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, literal_column, select
from sqlalchemy.orm import Session

from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import (
    BusinessRow,
    OperationalDayRow,
    PaymentRow,
    SaleItemRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id


@dataclass(frozen=True, slots=True)
class ExportLineRead:
    sale_session_id: UUID
    sale_confirmed_at: datetime
    sale_item_id: UUID
    product_name: str
    source_type: str
    product_id: UUID | None
    quantity: Decimal
    unit: str
    catalog_unit_price: Decimal | None
    unit_price: Decimal
    price_override_reason: str | None
    line_total: Decimal
    currency: str
    payment_id: UUID | None
    payment_method: str | None
    payment_amount: Decimal | None
    payment_currency: str | None


@dataclass(frozen=True, slots=True)
class ExportDayRead:
    business_name: str
    business_currency: str
    day_id: UUID
    business_date: date
    timezone_name: str
    status: str
    broken_sale_count: int
    lines: tuple[ExportLineRead, ...]


class SalesExportRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def load(
        self,
        *,
        tenant: TenantContext,
        day_id: UUID | None = None,
        business_date: date | None = None,
    ) -> ExportDayRead | None:
        """Return the day and its confirmed lines from a single SELECT.

        `day_id` and `business_date` are mutually exclusive filters. A missing
        day yields None. An existing day with no confirmed items yields an
        empty `lines` tuple.
        """
        if tenant is None:  # type: ignore[truthy-bool]
            raise ValidationAppError("tenant is required")
        if (day_id is None) == (business_date is None):
            raise ValidationAppError("export requires exactly one day selector")
        set_current_business_id(self._session, tenant.business_id)

        # Correlated to the outer operational_days row. A separate FROM of that
        # table would count broken sales on every day the tenant can see.
        broken_count = literal_column(
            """(
                SELECT count(*)
                FROM (
                    SELECT s.id
                    FROM sales.sale_sessions s
                    LEFT JOIN sales.payments p
                      ON p.sale_session_id = s.id AND p.business_id = s.business_id
                    LEFT JOIN sales.sale_items i
                      ON i.sale_session_id = s.id AND i.business_id = s.business_id
                    WHERE s.operational_day_id = operations.operational_days.id
                      AND s.business_id = operations.operational_days.business_id
                      AND s.status = 'confirmed'
                    GROUP BY s.id
                    HAVING count(i.id) = 0
                       OR count(DISTINCT p.id) FILTER (WHERE p.status = 'recorded') <> 1
                ) broken_sales
            )"""
        )

        statement = (
            select(
                OperationalDayRow.id,
                OperationalDayRow.business_date,
                OperationalDayRow.timezone,
                OperationalDayRow.status,
                BusinessRow.name,
                BusinessRow.currency,
                broken_count,
                SaleSessionRow.id,
                SaleSessionRow.confirmed_at,
                SaleItemRow.id,
                SaleItemRow.product_name_snapshot,
                SaleItemRow.source_type,
                SaleItemRow.product_id,
                SaleItemRow.quantity_normalized,
                SaleItemRow.unit_normalized,
                SaleItemRow.catalog_unit_price_snapshot,
                SaleItemRow.unit_price,
                SaleItemRow.price_override_reason,
                SaleItemRow.line_total,
                SaleItemRow.currency,
                PaymentRow.id,
                PaymentRow.method,
                PaymentRow.amount,
                PaymentRow.currency,
            )
            .select_from(OperationalDayRow)
            .join(BusinessRow, BusinessRow.id == OperationalDayRow.business_id)
            .outerjoin(
                SaleSessionRow,
                and_(
                    SaleSessionRow.operational_day_id == OperationalDayRow.id,
                    SaleSessionRow.business_id == OperationalDayRow.business_id,
                    SaleSessionRow.status == "confirmed",
                ),
            )
            .outerjoin(
                SaleItemRow,
                and_(
                    SaleItemRow.sale_session_id == SaleSessionRow.id,
                    SaleItemRow.business_id == SaleSessionRow.business_id,
                ),
            )
            .outerjoin(
                PaymentRow,
                and_(
                    PaymentRow.sale_session_id == SaleSessionRow.id,
                    PaymentRow.business_id == SaleSessionRow.business_id,
                    PaymentRow.status == "recorded",
                ),
            )
            .where(OperationalDayRow.business_id == tenant.business_id)
            .order_by(
                SaleSessionRow.confirmed_at.asc().nulls_last(),
                SaleSessionRow.id.asc().nulls_last(),
                SaleItemRow.created_at.asc().nulls_last(),
                SaleItemRow.id.asc().nulls_last(),
            )
        )
        if day_id is not None:
            statement = statement.where(OperationalDayRow.id == day_id)
        else:
            statement = statement.where(OperationalDayRow.business_date == business_date)

        rows = self._session.execute(statement).all()
        if not rows:
            return None
        first = rows[0]
        lines: list[ExportLineRead] = []
        for row in rows:
            if row[9] is None:
                continue
            lines.append(
                ExportLineRead(
                    sale_session_id=row[7],
                    sale_confirmed_at=row[8],
                    sale_item_id=row[9],
                    product_name=row[10],
                    source_type=row[11],
                    product_id=row[12],
                    quantity=row[13],
                    unit=row[14],
                    catalog_unit_price=row[15],
                    unit_price=row[16],
                    price_override_reason=row[17],
                    line_total=row[18],
                    currency=row[19],
                    payment_id=row[20],
                    payment_method=row[21],
                    payment_amount=row[22],
                    payment_currency=row[23],
                )
            )
        return ExportDayRead(
            business_name=first[4],
            business_currency=first[5],
            day_id=first[0],
            business_date=first[1],
            timezone_name=first[2],
            status=first[3],
            broken_sale_count=int(first[6] or 0),
            lines=tuple(lines),
        )
