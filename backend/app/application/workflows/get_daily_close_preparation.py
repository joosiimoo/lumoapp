from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.ports import IdentityPort
from app.domain.operations import (
    CashCount,
    ClosingSnapshot,
    DaySummaryTotals,
    InvalidBusinessTimezone,
    OperationalDay,
    OperationalDayStatus,
    business_date_for,
    cash_difference,
    cash_status_for,
    preparation_fingerprint,
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
    "confirmation_token",
)

CONFIRMED_DATA_KEYS = (
    "operational_day_id",
    "closing_snapshot_id",
    "business_date",
    "day_status",
    "closed_at",
    "currency",
    "sale_count",
    "gross_sales_total",
    "expected_cash",
    "counted_cash",
    "cash_difference",
    "cash_status",
)

NO_OPEN_DAY_TEXT = "No hay una jornada abierta para cerrar hoy."
CASH_COUNT_REQUIRED_TEXT = "Falta contar el efectivo antes de cerrar."
STALE_CONFIRMATION_TEXT = "El cierre cambió. Revisa los datos y confírmalo otra vez."


def build_close_preparation(
    *,
    business_date: date,
    currency: str,
    day: OperationalDay | None,
    sale_count: int,
    expected_cash: str,
    count: CashCount | None,
    totals: DaySummaryTotals | None = None,
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
        "confirmation_token": None,
    }
    if totals is not None:
        payload["_gross_sales_total"] = Money(totals.gross_sales_total, currency).to_json()
        payload["_cash_total"] = Money(totals.cash_total, currency).to_json()
        payload["_card_total"] = Money(totals.card_total, currency).to_json()
        payload["_transfer_total"] = Money(totals.transfer_total, currency).to_json()
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


def confirmed_ui_data(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: payload[key] for key in CONFIRMED_DATA_KEYS}


def request_close_text(payload: dict[str, Any]) -> str:
    count = int(payload["sale_count"])
    noun = "venta" if count == 1 else "ventas"
    gross = _amount_text(payload["_gross_sales_total"])
    expected = _amount_text(payload["expected_cash"])
    counted = _amount_text(payload["counted_cash"])
    difference = _amount_text(payload["cash_difference"])
    return (
        f"El cierre está preparado: {count} {noun} · {gross}. "
        f"Efectivo esperado {expected}. Contado {counted}. Diferencia {difference}. "
        "¿Confirmas el cierre?"
    )


def fingerprint_for_preparation(payload: dict[str, Any], *, business_id: UUID) -> str:
    return preparation_fingerprint(
        business_id=business_id,
        operational_day_id=UUID(str(payload["operational_day_id"])),
        cash_count_id=UUID(str(payload["cash_count_id"])),
        business_date=date.fromisoformat(payload["business_date"]),
        currency=payload["currency"],
        sale_count=int(payload["sale_count"]),
        gross_sales_total=payload["_gross_sales_total"]["amount"],
        cash_total=payload["_cash_total"]["amount"],
        card_total=payload["_card_total"]["amount"],
        transfer_total=payload["_transfer_total"]["amount"],
        expected_cash=payload["expected_cash"]["amount"],
        counted_cash=payload["counted_cash"]["amount"],
        cash_difference=payload["cash_difference"]["amount"],
        cash_status=payload["cash_status"],
    )


def build_confirmed_close(snapshot: ClosingSnapshot) -> dict[str, Any]:
    currency = snapshot.currency
    payload: dict[str, Any] = {
        "operational_day_id": str(snapshot.operational_day_id),
        "closing_snapshot_id": str(snapshot.id),
        "business_date": snapshot.business_date.isoformat(),
        "day_status": OperationalDayStatus.CLOSED.value,
        "closed_at": snapshot.closed_at.isoformat(),
        "currency": currency,
        "sale_count": snapshot.sale_count,
        "gross_sales_total": Money(snapshot.gross_sales_total, currency).to_json(),
        "expected_cash": Money(snapshot.expected_cash, currency).to_json(),
        "counted_cash": Money(snapshot.counted_cash, currency).to_json(),
        "cash_difference": Money(snapshot.cash_difference, currency).to_json(),
        "cash_status": snapshot.cash_status.value,
        "cash_count_id": str(snapshot.cash_count_id),
    }
    payload["text"] = confirmed_close_text(payload)
    return payload


def confirmed_close_text(payload: dict[str, Any]) -> str:
    count = int(payload["sale_count"])
    noun = "venta" if count == 1 else "ventas"
    word = CASH_STATUS_WORDS[payload["cash_status"]]
    return (
        f"Cierre confirmado · {payload['business_date']} · {count} {noun}"
        f" · {_amount_text(payload['gross_sales_total'])}"
        f" · Efectivo esperado {_amount_text(payload['expected_cash'])}"
        f" · Contado {_amount_text(payload['counted_cash'])}"
        f" · Diferencia {_amount_text(payload['cash_difference'])}"
        f" · {word}"
    )


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
        if day.status is OperationalDayStatus.CLOSED:
            snapshot = self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
            if snapshot is None:
                raise ValidationAppError("closed day is missing its closing snapshot")
            return build_confirmed_close(snapshot)
        totals = self._operations.summarize_day(
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
            expected_cash=totals.cash_total,
            count=count,
            totals=totals,
        )


def _amount_text(money: dict[str, str]) -> str:
    amount = money["amount"]
    if amount.startswith("-"):
        return f"-${amount[1:]}"
    return f"${amount}"
