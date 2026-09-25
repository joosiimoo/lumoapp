from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.operations.cash_count import CashStatus
from app.domain.operations.day import OperationalDayStatus

OUTCOME_TYPE_DAILY_CLOSE_READY = "daily_close_ready"
OUTCOME_VERSION = 1
OUTCOME_DEFINITION_ID = "daily_close_ready@1"
OWNER_TYPE_BUSINESS = "business"
TRIGGER_FIRST_CONFIRMED_SALE = "first_confirmed_sale"
OUTPUT_ARTIFACT_CLOSING_SNAPSHOT = "ClosingSnapshot"

_TWO_PLACES = Decimal("0.01")


class OutcomeRunStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    READY = "ready"
    COMPLETED = "completed"


class OutcomeReasonCode(StrEnum):
    AWAITING_CASH_COUNT = "awaiting_cash_count"
    READY_BALANCED = "ready_balanced"
    READY_CASH_SHORT = "ready_cash_short"
    READY_CASH_OVER = "ready_cash_over"
    CLOSED_CONFIRMED = "closed_confirmed"


_REASON_FOR_CASH = {
    CashStatus.BALANCED: OutcomeReasonCode.READY_BALANCED,
    CashStatus.SHORT: OutcomeReasonCode.READY_CASH_SHORT,
    CashStatus.OVER: OutcomeReasonCode.READY_CASH_OVER,
}


@dataclass(frozen=True, slots=True)
class OutcomeVerdict:
    status: OutcomeRunStatus
    reason_code: OutcomeReasonCode


@dataclass(frozen=True, slots=True)
class OutcomeRun:
    id: UUID
    business_id: UUID
    operational_day_id: UUID
    outcome_type: str
    outcome_version: int
    status: OutcomeRunStatus
    owner_type: str
    reason_code: str
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    ready_at: datetime | None = None
    completed_at: datetime | None = None
    closing_snapshot_id: UUID | None = None


def derive_daily_close_outcome(
    *,
    day_status: OperationalDayStatus | None,
    sale_count: int,
    cash_status: CashStatus | None,
    has_snapshot: bool,
) -> OutcomeVerdict | None:
    """Deterministic Daily Close outcome. WorkItems do not enter this predicate."""
    if day_status is OperationalDayStatus.CLOSED and has_snapshot:
        return OutcomeVerdict(OutcomeRunStatus.COMPLETED, OutcomeReasonCode.CLOSED_CONFIRMED)
    if day_status is not OperationalDayStatus.OPEN or sale_count < 1:
        return None
    if cash_status is None or cash_status is CashStatus.NOT_COUNTED:
        return OutcomeVerdict(OutcomeRunStatus.IN_PROGRESS, OutcomeReasonCode.AWAITING_CASH_COUNT)
    reason = _REASON_FOR_CASH.get(cash_status)
    if reason is None:
        return None
    return OutcomeVerdict(OutcomeRunStatus.READY, reason)


def outcome_evidence(
    *,
    currency: str,
    sale_count: int,
    gross_sales_total: str,
    expected_cash: str,
    cash_status: CashStatus,
    counted_cash: Decimal | None = None,
    cash_difference_amount: Decimal | None = None,
    current_cash_count_id: UUID | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "currency": currency,
        "sale_count": sale_count,
        "gross_sales_total": _decimal_string(gross_sales_total),
        "expected_cash": _decimal_string(expected_cash),
        "cash_status": cash_status.value,
    }
    if counted_cash is None:
        return payload
    payload["counted_cash"] = _decimal_string(counted_cash)
    payload["cash_difference"] = _decimal_string(cash_difference_amount or Decimal("0"))
    payload["current_cash_count_id"] = str(current_cash_count_id)
    return payload


def evaluate_daily_close_ready(confirmed_state: dict[str, Any]) -> OutcomeVerdict | None:
    """Gate evaluator for daily_close_ready@1. Ignores any model claim held by the caller."""
    day_raw = confirmed_state.get("day_status")
    day_status = OperationalDayStatus(day_raw) if day_raw else None
    cash_raw = confirmed_state.get("cash_status")
    cash_status = CashStatus(cash_raw) if cash_raw else None
    return derive_daily_close_outcome(
        day_status=day_status,
        sale_count=int(confirmed_state.get("sale_count") or 0),
        cash_status=cash_status,
        has_snapshot=bool(confirmed_state.get("has_snapshot")),
    )


def daily_close_ready_definition() -> dict[str, Any]:
    return {
        "id": OUTCOME_DEFINITION_ID,
        "outcome_type": OUTCOME_TYPE_DAILY_CLOSE_READY,
        "version": OUTCOME_VERSION,
        "owner_type": OWNER_TYPE_BUSINESS,
        "trigger": TRIGGER_FIRST_CONFIRMED_SALE,
        "output_artifact": OUTPUT_ARTIFACT_CLOSING_SNAPSHOT,
        "states": [status.value for status in OutcomeRunStatus],
        "gate_evaluator": evaluate_daily_close_ready,
    }


def _decimal_string(value: Decimal | str) -> str:
    amount = value if isinstance(value, Decimal) else Decimal(value)
    return format(amount.quantize(_TWO_PLACES), "f")
