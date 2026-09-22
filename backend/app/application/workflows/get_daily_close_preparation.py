from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.application.ports import IdentityPort
from app.domain.operations import (
    CashCount,
    InvalidBusinessTimezone,
    OperationalDay,
    business_date_for,
    cash_difference,
    cash_status_for,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository

CASH_STATUS_WORDS = {
    "not_counted": "Sin contar",
    "balanced": "Caja cuadrada",
    "over": "Sobrante",
    "short": "Faltante",
}

PREPARATION_DATA_KEYS = (
    "operational_day_id",
    "business_date",
    "day_status",
    "currency",
    "sale_count",
    "expected_cash",
    "counted_cash",
    "cash_difference",
    "cash_status",
    "counted_at",
    "cash_count_id",
)


def build_close_preparation(
    *,
    business_date: date,
    currency: str,
    day: OperationalDay | None,
    sale_count: int,
    expected_cash: str,
    count: CashCount | None,
) -> dict[str, Any]:
    """The one close-preparation payload. Both the read and the write return this shape."""
    expected = Money(expected_cash, currency).to_json()
    counted_amount = count.amount if count is not None else None
    difference = cash_difference(Decimal(expected["amount"]), counted_amount)
    status = cash_status_for(difference)
    payload: dict[str, Any] = {
        "operational_day_id": str(day.id) if day is not None else None,
        "business_date": business_date.isoformat(),
        "day_status": day.status.value if day is not None else None,
        "currency": currency,
        "sale_count": sale_count,
        "expected_cash": expected,
        "counted_cash": Money(counted_amount, currency).to_json() if counted_amount is not None else None,
        "cash_difference": Money(difference, currency).to_json() if difference is not None else None,
        "cash_status": status.value,
        "counted_at": count.counted_at.isoformat() if count is not None else None,
        "cash_count_id": str(count.id) if count is not None else None,
    }
    payload["text"] = close_preparation_text(payload)
    return payload


def close_preparation_text(payload: dict[str, Any]) -> str:
    business_date = payload["business_date"]
    expected = _amount_text(payload["expected_cash"])
    if payload["cash_status"] == "not_counted":
        return f"Cierre {business_date} · Efectivo esperado {expected} · Falta contar efectivo"
    counted = _amount_text(payload["counted_cash"])
    difference = _amount_text(payload["cash_difference"])
    word = CASH_STATUS_WORDS[payload["cash_status"]]
    return (
        f"Cierre {business_date} · Efectivo esperado {expected}"
        f" · Contado {counted} · Diferencia {difference} · {word}"
    )


def preparation_ui_data(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in PREPARATION_DATA_KEYS}


def business_date_now(*, timezone_name: str, now: datetime | None) -> tuple[datetime, date]:
    instant = now if now is not None else utcnow()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationAppError("clock must be timezone-aware UTC")
    instant = instant.astimezone(UTC)
    try:
        return instant, business_date_for(instant, timezone_name)
    except InvalidBusinessTimezone as exc:
        raise ValidationAppError("invalid business timezone") from exc


class GetDailyClosePreparation:
    """closing.prepare@1. Pure read: it never inserts or updates a row."""

    def __init__(self, *, identities: IdentityPort, operations: OperationsRepository) -> None:
        self._identities = identities
        self._operations = operations

    def execute(self, *, tenant: TenantContext, now: datetime | None = None) -> dict[str, Any]:
        business = self._identities.get_business(tenant)
        _instant, business_date = business_date_now(timezone_name=business.timezone, now=now)
        day = self._operations.get_by_date(tenant=tenant, business_date=business_date)
        if day is None:
            return build_close_preparation(
                business_date=business_date,
                currency=business.currency,
                day=None,
                sale_count=0,
                expected_cash="0.00",
                count=None,
            )
        totals = self._operations.summarize_day(
            tenant=tenant,
            operational_day_id=day.id,
            currency=business.currency,
        )
        expected_cash = self._operations.expected_cash(
            tenant=tenant,
            operational_day_id=day.id,
            currency=business.currency,
        )
        count = self._operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
        return build_close_preparation(
            business_date=business_date,
            currency=business.currency,
            day=day,
            sale_count=totals.sale_count,
            expected_cash=expected_cash,
            count=count,
        )


def _amount_text(money: dict[str, str]) -> str:
    amount = money["amount"]
    if amount.startswith("-"):
        return f"-${amount[1:]}"
    return f"${amount}"
