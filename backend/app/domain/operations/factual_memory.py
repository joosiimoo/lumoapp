"""Closed factual-memory read model. No I/O, prose, score, or embedding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.operations.business_event import BusinessEvent
from app.domain.shared.errors import ValidationAppError

LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS = "only_lumo_registered_operations"
RECENT_DAYS_MIN = 1
RECENT_DAYS_MAX = 30

_DAY_SCOPED = frozenset(
    {
        "day_summary",
        "day_events",
        "sales_summary",
        "cash_summary",
        "close_summary",
    }
)


class FactualQueryType(StrEnum):
    DAY_SUMMARY = "day_summary"
    DAY_EVENTS = "day_events"
    SALES_SUMMARY = "sales_summary"
    CASH_SUMMARY = "cash_summary"
    CLOSE_SUMMARY = "close_summary"
    LATEST_CLOSE = "latest_close"
    RECENT_CASH_DIFFERENCES = "recent_cash_differences"


class FactualEmptyReason(StrEnum):
    NO_OPERATIONAL_DAY = "no_operational_day"
    NO_CONFIRMED_SALES = "no_confirmed_sales"
    NO_CASH_COUNT = "no_cash_count"
    NO_COMPLETED_CLOSE = "no_completed_close"
    NO_MATCHING_FACTS = "no_matching_facts"


def recent_days_in_range(value: object) -> int:
    """Pure check. 1 through 30 inclusive. Booleans are not integers here."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationAppError("recent_days must be from 1 to 30")
    if value < RECENT_DAYS_MIN or value > RECENT_DAYS_MAX:
        raise ValidationAppError("recent_days must be from 1 to 30")
    return value


def business_date_is_future(business_date: date, business_today: date) -> bool:
    """A future business-local date is not a day Lumo may create from a read."""
    return business_date > business_today


@dataclass(frozen=True, slots=True)
class FactualMemoryQuery:
    query_type: FactualQueryType
    business_date: date | None = None
    recent_days: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.query_type, FactualQueryType):
            raise ValidationAppError("factual query type is not supported")
        name = self.query_type.value
        if name in _DAY_SCOPED:
            if self.business_date is None or self.recent_days is not None:
                raise ValidationAppError("a day-scoped factual query requires business_date only")
            return
        if name == FactualQueryType.LATEST_CLOSE.value:
            if self.business_date is not None or self.recent_days is not None:
                raise ValidationAppError("latest_close does not accept a date or a window")
            return
        if self.business_date is not None or self.recent_days is None:
            raise ValidationAppError("recent_cash_differences requires recent_days only")
        object.__setattr__(self, "recent_days", recent_days_in_range(self.recent_days))


@dataclass(frozen=True, slots=True)
class BusinessEventRead:
    event_id: UUID
    event_type: str
    business_date: date
    occurred_at: datetime
    source_type: str
    source_entity_type: str
    source_entity_id: UUID
    facts: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "business_date": self.business_date.isoformat(),
            "occurred_at": self.occurred_at.isoformat(),
            "source_type": self.source_type,
            "source_entity_type": self.source_entity_type,
            "source_entity_id": str(self.source_entity_id),
            "facts": dict(self.facts),
        }


@dataclass(frozen=True, slots=True)
class DatedBusinessEvent:
    """Repository row plus the operational day's business date and timezone."""

    event: BusinessEvent
    business_date: date
    timezone_name: str


@dataclass(frozen=True, slots=True)
class SaleEventRef:
    event_id: UUID
    sale_session_id: UUID

    def to_dict(self) -> dict[str, str]:
        return {"event_id": str(self.event_id), "sale_session_id": str(self.sale_session_id)}


@dataclass(frozen=True, slots=True)
class DaySummaryFacts:
    day_status: str
    sale_count: int
    gross_sales_total: str
    cash_sales_total: str
    card_sales_total: str
    transfer_sales_total: str
    expected_cash: str | None
    counted_cash: str | None
    cash_difference: str | None
    cash_status: str | None
    close_status: str
    pending_work_count: int
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "day_status": self.day_status,
            "sale_count": self.sale_count,
            "gross_sales_total": self.gross_sales_total,
            "cash_sales_total": self.cash_sales_total,
            "card_sales_total": self.card_sales_total,
            "transfer_sales_total": self.transfer_sales_total,
            "expected_cash": self.expected_cash,
            "counted_cash": self.counted_cash,
            "cash_difference": self.cash_difference,
            "cash_status": self.cash_status,
            "close_status": self.close_status,
            "pending_work_count": self.pending_work_count,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class SalesSummaryFacts:
    sale_count: int
    gross_sales_total: str
    cash_sales_total: str
    card_sales_total: str
    transfer_sales_total: str
    currency: str
    sale_event_refs: tuple[SaleEventRef, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "sale_count": self.sale_count,
            "gross_sales_total": self.gross_sales_total,
            "cash_sales_total": self.cash_sales_total,
            "card_sales_total": self.card_sales_total,
            "transfer_sales_total": self.transfer_sales_total,
            "currency": self.currency,
        }
        body["sale_event_refs"] = [ref.to_dict() for ref in self.sale_event_refs]
        return body


@dataclass(frozen=True, slots=True)
class CashSummaryFacts:
    expected_cash: str
    counted_cash: str
    cash_difference: str
    cash_status: str
    currency: str
    counted_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected_cash": self.expected_cash,
            "counted_cash": self.counted_cash,
            "cash_difference": self.cash_difference,
            "cash_status": self.cash_status,
            "currency": self.currency,
            "counted_at": None if self.counted_at is None else self.counted_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class CloseSummaryFacts:
    business_date: date
    closed_at: datetime
    sale_count: int
    gross_sales_total: str
    expected_cash: str
    counted_cash: str
    cash_difference: str
    cash_status: str
    outcome_status: str | None
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_date": self.business_date.isoformat(),
            "closed_at": self.closed_at.isoformat(),
            "sale_count": self.sale_count,
            "gross_sales_total": self.gross_sales_total,
            "expected_cash": self.expected_cash,
            "counted_cash": self.counted_cash,
            "cash_difference": self.cash_difference,
            "cash_status": self.cash_status,
            "outcome_status": self.outcome_status,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class CashDifferenceFact:
    business_date: date
    expected_cash: str
    counted_cash: str
    cash_difference: str
    cash_status: str
    closed_at: datetime
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_date": self.business_date.isoformat(),
            "expected_cash": self.expected_cash,
            "counted_cash": self.counted_cash,
            "cash_difference": self.cash_difference,
            "cash_status": self.cash_status,
            "closed_at": self.closed_at.isoformat(),
            "currency": self.currency,
        }


FactualFacts = (
    DaySummaryFacts
    | SalesSummaryFacts
    | CashSummaryFacts
    | CloseSummaryFacts
    | tuple[CashDifferenceFact, ...]
)


@dataclass(frozen=True, slots=True)
class FactualMemoryResult:
    query_type: FactualQueryType
    business_id: UUID
    business_date: date | None
    period_start: date | None
    period_end: date | None
    facts: FactualFacts | None
    events: tuple[BusinessEventRead, ...]
    source_coverage: dict[str, Any] | None
    limitation_code: str
    empty_reason: FactualEmptyReason | None

    def __post_init__(self) -> None:
        if self.limitation_code != LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS:
            raise ValidationAppError("factual memory limitation is only_lumo_registered_operations")
        if self.empty_reason is not None and self.facts is not None:
            raise ValidationAppError("an empty factual result does not carry facts")

    def to_dict(self) -> dict[str, Any]:
        facts: Any
        if self.facts is None:
            facts = None
        elif isinstance(self.facts, tuple):
            facts = [item.to_dict() for item in self.facts]
        else:
            facts = self.facts.to_dict()
        return {
            "query_type": self.query_type.value,
            "business_id": str(self.business_id),
            "business_date": None if self.business_date is None else self.business_date.isoformat(),
            "period_start": None if self.period_start is None else self.period_start.isoformat(),
            "period_end": None if self.period_end is None else self.period_end.isoformat(),
            "facts": facts,
            "events": [event.to_dict() for event in self.events],
            "source_coverage": self.source_coverage,
            "limitation_code": self.limitation_code,
            "empty_reason": None if self.empty_reason is None else self.empty_reason.value,
        }
