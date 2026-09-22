from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.application.ports import IdentityPort
from app.domain.operations import InvalidBusinessTimezone, business_date_for
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository


class GetOperationalDaySummary:
    def __init__(self, *, identities: IdentityPort, operations: OperationsRepository) -> None:
        self._identities = identities
        self._operations = operations

    def execute(self, *, tenant: TenantContext, now: datetime | None = None) -> dict[str, Any]:
        business = self._identities.get_business(tenant)
        instant = now if now is not None else utcnow()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValidationAppError("clock must be timezone-aware UTC")
        instant = instant.astimezone(UTC)
        try:
            business_date = business_date_for(instant, business.timezone)
        except InvalidBusinessTimezone as exc:
            raise ValidationAppError("invalid business timezone") from exc
        day = self._operations.get_by_date(tenant=tenant, business_date=business_date)
        if day is None:
            payload = _zero_payload(business_date=business_date, currency=business.currency)
        else:
            totals = self._operations.summarize_day(
                tenant=tenant,
                operational_day_id=day.id,
                currency=business.currency,
            )
            payload = {
                "operational_day_id": str(day.id),
                "business_date": day.business_date.isoformat(),
                "status": day.status.value,
                "currency": totals.currency,
                "sale_count": totals.sale_count,
                "gross_sales_total": totals.gross_sales_total,
                "cash_total": totals.cash_total,
                "card_total": totals.card_total,
                "transfer_total": totals.transfer_total,
            }
        payload["text"] = _fallback_text(payload)
        return payload


def _zero_payload(*, business_date, currency: str) -> dict[str, Any]:
    zero = Money("0.00", currency).to_json()["amount"]
    return {
        "operational_day_id": None,
        "business_date": business_date.isoformat(),
        "status": None,
        "currency": currency,
        "sale_count": 0,
        "gross_sales_total": zero,
        "cash_total": zero,
        "card_total": zero,
        "transfer_total": zero,
    }


def _fallback_text(payload: dict[str, Any]) -> str:
    count = int(payload["sale_count"])
    noun = "venta" if count == 1 else "ventas"
    return (
        f"Hoy {payload['business_date']} · {count} {noun} · ${payload['gross_sales_total']}"
        f" · Efectivo ${payload['cash_total']} · Tarjeta ${payload['card_total']}"
        f" · Transferencia ${payload['transfer_total']}"
    )
