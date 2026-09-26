from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.shared.errors import ValidationAppError

_TWO_PLACES = Decimal("0.01")
_PAYMENT_METHODS = frozenset({"cash", "card", "transfer"})
_CASH_STATUSES = frozenset({"balanced", "short", "over"})

SALE_CONFIRMED_FACT_KEYS = frozenset(
    {"sale_session_id", "payment_id", "payment_method", "amount", "currency"}
)
CASH_COUNT_RECORDED_FACT_KEYS = frozenset(
    {"cash_count_id", "expected_cash", "counted_cash", "cash_difference", "cash_status", "currency"}
)
DAILY_CLOSE_COMPLETED_FACT_KEYS = frozenset(
    {
        "outcome_run_id",
        "closing_snapshot_id",
        "sale_count",
        "gross_sales_total",
        "expected_cash",
        "counted_cash",
        "cash_difference",
        "cash_status",
        "currency",
    }
)


class BusinessEventType(StrEnum):
    SALE_CONFIRMED = "sale_confirmed"
    CASH_COUNT_RECORDED = "cash_count_recorded"
    DAILY_CLOSE_COMPLETED = "daily_close_completed"


class BusinessEventSourceType(StrEnum):
    """Primary operational data source of the confirmed fact. Not the writer or route."""

    MANUAL_CAPTURE = "manual_capture"


class SourceEntityType(StrEnum):
    SALE_SESSION = "sale_session"
    CASH_COUNT = "cash_count"
    CLOSING_SNAPSHOT = "closing_snapshot"


_ENTITY_FOR_EVENT = {
    BusinessEventType.SALE_CONFIRMED: SourceEntityType.SALE_SESSION,
    BusinessEventType.CASH_COUNT_RECORDED: SourceEntityType.CASH_COUNT,
    BusinessEventType.DAILY_CLOSE_COMPLETED: SourceEntityType.CLOSING_SNAPSHOT,
}
_KEYS_FOR_EVENT = {
    BusinessEventType.SALE_CONFIRMED: SALE_CONFIRMED_FACT_KEYS,
    BusinessEventType.CASH_COUNT_RECORDED: CASH_COUNT_RECORDED_FACT_KEYS,
    BusinessEventType.DAILY_CLOSE_COMPLETED: DAILY_CLOSE_COMPLETED_FACT_KEYS,
}
_ID_FACT_FOR_EVENT = {
    BusinessEventType.SALE_CONFIRMED: "sale_session_id",
    BusinessEventType.CASH_COUNT_RECORDED: "cash_count_id",
    BusinessEventType.DAILY_CLOSE_COMPLETED: "closing_snapshot_id",
}


@dataclass(frozen=True, slots=True)
class BusinessEvent:
    id: UUID
    business_id: UUID
    operational_day_id: UUID
    event_type: BusinessEventType
    occurred_at: datetime
    source_type: BusinessEventSourceType
    source_entity_type: SourceEntityType
    source_entity_id: UUID
    facts: dict[str, Any]
    created_at: datetime

    def __post_init__(self) -> None:
        if self.operational_day_id is None:
            raise ValidationAppError("business event operational_day_id is required")
        if self.source_type is not BusinessEventSourceType.MANUAL_CAPTURE:
            raise ValidationAppError("business event source is manual_capture only")
        if not isinstance(self.event_type, BusinessEventType):
            raise ValidationAppError("business event type is not a Build A event")
        if _ENTITY_FOR_EVENT[self.event_type] is not self.source_entity_type:
            raise ValidationAppError("business event source entity does not match the event type")
        for stamp in (self.occurred_at, self.created_at):
            if stamp.tzinfo is None or stamp.utcoffset() is None:
                raise ValidationAppError("business event timestamps must be timezone-aware")
        object.__setattr__(
            self,
            "facts",
            validate_business_event_facts(
                event_type=self.event_type,
                source_entity_id=self.source_entity_id,
                facts=self.facts,
            ),
        )


def sale_confirmed_facts(
    *,
    sale_session_id: UUID,
    payment_id: UUID,
    payment_method: str,
    amount: Decimal | str,
    currency: str,
) -> dict[str, str]:
    if payment_method not in _PAYMENT_METHODS:
        raise ValidationAppError("payment_method is not a confirmed payment method")
    return {
        "sale_session_id": str(sale_session_id),
        "payment_id": str(payment_id),
        "payment_method": payment_method,
        "amount": decimal_fact(amount),
        "currency": _currency(currency),
    }


def cash_count_recorded_facts(
    *,
    cash_count_id: UUID,
    expected_cash: Decimal | str,
    counted_cash: Decimal | str,
    cash_difference_amount: Decimal | str,
    cash_status: str,
    currency: str,
) -> dict[str, str]:
    if cash_status not in _CASH_STATUSES:
        raise ValidationAppError("cash_status is not a counted status")
    return {
        "cash_count_id": str(cash_count_id),
        "expected_cash": decimal_fact(expected_cash),
        "counted_cash": decimal_fact(counted_cash),
        "cash_difference": decimal_fact(cash_difference_amount),
        "cash_status": cash_status,
        "currency": _currency(currency),
    }


def daily_close_completed_facts(
    *,
    outcome_run_id: UUID,
    closing_snapshot_id: UUID,
    sale_count: int,
    gross_sales_total: Decimal | str,
    expected_cash: Decimal | str,
    counted_cash: Decimal | str,
    cash_difference_amount: Decimal | str,
    cash_status: str,
    currency: str,
) -> dict[str, Any]:
    if isinstance(sale_count, bool) or not isinstance(sale_count, int):
        raise ValidationAppError("sale_count must be a JSON integer")
    if cash_status not in _CASH_STATUSES:
        raise ValidationAppError("cash_status is not a counted status")
    return {
        "outcome_run_id": str(outcome_run_id),
        "closing_snapshot_id": str(closing_snapshot_id),
        "sale_count": sale_count,
        "gross_sales_total": decimal_fact(gross_sales_total),
        "expected_cash": decimal_fact(expected_cash),
        "counted_cash": decimal_fact(counted_cash),
        "cash_difference": decimal_fact(cash_difference_amount),
        "cash_status": cash_status,
        "currency": _currency(currency),
    }


def validate_business_event_facts(
    *,
    event_type: BusinessEventType,
    source_entity_id: UUID,
    facts: dict[str, Any],
) -> dict[str, Any]:
    expected = _KEYS_FOR_EVENT[event_type]
    if set(facts) != expected:
        raise ValidationAppError("business event facts must contain the approved keys only")
    checked = dict(facts)
    id_key = _ID_FACT_FOR_EVENT[event_type]
    if checked[id_key] != str(source_entity_id):
        raise ValidationAppError("business event fact id does not match the source entity")
    if event_type is BusinessEventType.SALE_CONFIRMED:
        _require_uuid_text(checked["payment_id"], "payment_id")
        if checked["payment_method"] not in _PAYMENT_METHODS:
            raise ValidationAppError("payment_method is not a confirmed payment method")
        checked["amount"] = _require_money(checked["amount"])
        checked["currency"] = _currency(checked["currency"])
    elif event_type is BusinessEventType.CASH_COUNT_RECORDED:
        for key in ("expected_cash", "counted_cash", "cash_difference"):
            checked[key] = _require_money(checked[key])
        if checked["cash_status"] not in _CASH_STATUSES:
            raise ValidationAppError("cash_status is not a counted status")
        checked["currency"] = _currency(checked["currency"])
    else:
        _require_uuid_text(checked["outcome_run_id"], "outcome_run_id")
        if isinstance(checked["sale_count"], bool) or not isinstance(checked["sale_count"], int):
            raise ValidationAppError("sale_count must be a JSON integer")
        for key in ("gross_sales_total", "expected_cash", "counted_cash", "cash_difference"):
            checked[key] = _require_money(checked[key])
        if checked["cash_status"] not in _CASH_STATUSES:
            raise ValidationAppError("cash_status is not a counted status")
        checked["currency"] = _currency(checked["currency"])
    return checked


def decimal_fact(value: Decimal | str) -> str:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (Decimal, str)):
        raise ValidationAppError("money facts must be decimal strings")
    try:
        amount = value if isinstance(value, Decimal) else Decimal(value)
    except Exception as exc:
        raise ValidationAppError("money facts must be decimal strings") from exc
    rendered = format(amount.quantize(_TWO_PLACES), "f")
    if not _money_text(rendered):
        raise ValidationAppError("money facts require two fractional digits")
    return rendered


def _require_money(value: Any) -> str:
    if not isinstance(value, str) or not _money_text(value):
        raise ValidationAppError("money facts must be decimal strings")
    parsed = Decimal(value)
    if format(parsed.quantize(_TWO_PLACES), "f") != value:
        raise ValidationAppError("money facts require two fractional digits")
    return value


def _require_uuid_text(value: Any, field: str) -> None:
    if not isinstance(value, str):
        raise ValidationAppError(f"{field} must be a uuid string")
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise ValidationAppError(f"{field} must be a uuid string") from exc
    if str(parsed) != value:
        raise ValidationAppError(f"{field} must be a uuid string")


def _currency(value: str) -> str:
    if not isinstance(value, str) or len(value) != 3 or not value.isalpha() or value != value.upper():
        raise ValidationAppError("currency must be a 3-letter ISO 4217 code")
    return value


def _money_text(value: str) -> bool:
    if value.startswith("-"):
        body = value[1:]
    else:
        body = value
    whole, dot, fraction = body.partition(".")
    return bool(dot) and whole.isdigit() and len(fraction) == 2 and fraction.isdigit()
