"""Read-only factual memory. Domain tables stay authoritative. Events are chronology."""

from __future__ import annotations

import base64
import binascii
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from app.application.ports import IdentityPort
from app.domain.operations import (
    LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
    BusinessEvent,
    BusinessEventType,
    CashStatus,
    ClosingSnapshot,
    InvalidBusinessTimezone,
    OperationalDay,
    OperationalDayStatus,
    business_date_for,
    cash_difference,
    cash_status_for,
    recorded_operations_declaration,
)
from app.domain.operations.factual_memory import (
    BusinessEventRead,
    CashDifferenceFact,
    CashSummaryFacts,
    CloseSummaryFacts,
    DatedBusinessEvent,
    DaySummaryFacts,
    FactualEmptyReason,
    FactualMemoryQuery,
    FactualMemoryResult,
    FactualQueryType,
    SaleEventRef,
    SalesSummaryFacts,
    business_date_is_future,
    recent_days_in_range,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository

TIMELINE_WINDOW_DAYS = 7
TIMELINE_DEFAULT_LIMIT = 20
TIMELINE_MAX_LIMIT = 50
_DAY_SCOPED = frozenset(
    {
        FactualQueryType.DAY_SUMMARY,
        FactualQueryType.DAY_EVENTS,
        FactualQueryType.SALES_SUMMARY,
        FactualQueryType.CASH_SUMMARY,
        FactualQueryType.CLOSE_SUMMARY,
    }
)


class FactualMemoryService:
    def __init__(self, *, identities: IdentityPort, operations: OperationsRepository) -> None:
        self._identities = identities
        self._operations = operations

    def tool_arguments(
        self,
        *,
        tenant: TenantContext,
        now: datetime | None,
        query_type: FactualQueryType,
        scope: str,
        explicit_date: date | None = None,
        month: int | None = None,
        day: int | None = None,
        recent_days: int | None = None,
    ) -> dict[str, Any] | None:
        """Resolve today, yesterday, and omitted year before the tool runs."""
        query = prepare_factual_query(
            query_type=query_type,
            scope=scope,
            business_today=self._business_today(tenant, now),
            explicit_date=explicit_date,
            month=month,
            day=day,
            recent_days=recent_days,
        )
        if query is None:
            return None
        arguments: dict[str, Any] = {"query_type": query.query_type.value}
        if query.business_date is not None:
            arguments["business_date"] = query.business_date.isoformat()
        if query.recent_days is not None:
            arguments["recent_days"] = query.recent_days
        return arguments

    def execute(
        self,
        *,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        now: datetime | None = None,
    ) -> FactualMemoryResult:
        business_today = self._business_today(tenant, now)
        if query.query_type in _DAY_SCOPED and query.business_date is not None:
            if business_date_is_future(query.business_date, business_today):
                return self._empty_day(tenant, query, FactualEmptyReason.NO_OPERATIONAL_DAY)
        if query.query_type is FactualQueryType.LATEST_CLOSE:
            return self._latest_close(tenant)
        if query.query_type is FactualQueryType.RECENT_CASH_DIFFERENCES:
            return self._recent_differences(tenant, query, business_today)
        assert query.business_date is not None
        day = self._operations.get_by_date(tenant=tenant, business_date=query.business_date)
        if day is None:
            return self._empty_day(tenant, query, FactualEmptyReason.NO_OPERATIONAL_DAY)
        if query.query_type is FactualQueryType.DAY_SUMMARY:
            return self._day_summary(tenant, query, day)
        if query.query_type is FactualQueryType.DAY_EVENTS:
            return self._day_events(tenant, query, day)
        if query.query_type is FactualQueryType.SALES_SUMMARY:
            return self._sales_summary(tenant, query, day)
        if query.query_type is FactualQueryType.CASH_SUMMARY:
            return self._cash_summary(tenant, query, day)
        return self._close_summary(tenant, query, day)

    def list_timeline(
        self,
        *,
        tenant: TenantContext,
        limit: int = TIMELINE_DEFAULT_LIMIT,
        before: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > TIMELINE_MAX_LIMIT:
            raise ValidationAppError("limit must be from 1 to 50")
        business_today = self._business_today(tenant, now)
        period_start = business_today - timedelta(days=TIMELINE_WINDOW_DAYS - 1)
        cursor = _decode_cursor(before) if before else None
        if cursor is not None and not _cursor_inside_window(
            cursor[0],
            period_start=period_start,
            period_end=business_today,
            timezone_name=self._identities.get_business(tenant).timezone,
        ):
            return {
                "events": [],
                "next_cursor": None,
                "business_today": business_today.isoformat(),
                "business_yesterday": (business_today - timedelta(days=1)).isoformat(),
            }
        rows = self._operations.list_recent_business_events(
            tenant=tenant,
            period_start=period_start,
            period_end=business_today,
            limit=limit + 1,
            before_occurred_at=None if cursor is None else cursor[0],
            before_id=None if cursor is None else cursor[1],
        )
        page = rows[:limit]
        next_cursor = _encode_cursor(page[-1]) if len(rows) > limit and page else None
        events = [_timeline_event(row) for row in page]
        return {
            "events": events,
            "next_cursor": next_cursor,
            "business_today": business_today.isoformat(),
            "business_yesterday": (business_today - timedelta(days=1)).isoformat(),
        }

    def _business_today(self, tenant: TenantContext, now: datetime | None) -> date:
        business = self._identities.get_business(tenant)
        instant = now if now is not None else utcnow()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValidationAppError("clock must be timezone-aware UTC")
        instant = instant.astimezone(UTC)
        try:
            return business_date_for(instant, business.timezone)
        except InvalidBusinessTimezone as exc:
            raise ValidationAppError("invalid business timezone") from exc

    def _currency(self, tenant: TenantContext) -> str:
        return self._identities.get_business(tenant).currency

    def _empty_day(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        reason: FactualEmptyReason,
    ) -> FactualMemoryResult:
        return FactualMemoryResult(
            query_type=query.query_type,
            business_id=tenant.business_id,
            business_date=query.business_date,
            period_start=query.business_date,
            period_end=query.business_date,
            facts=None,
            events=(),
            source_coverage=None,
            limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
            empty_reason=reason,
        )

    def _coverage(self, tenant: TenantContext, day: OperationalDay) -> dict[str, Any]:
        records = self._operations.list_source_coverage(tenant=tenant, operational_day_id=day.id)
        return recorded_operations_declaration(records)

    def _events(self, tenant: TenantContext, day: OperationalDay) -> tuple[BusinessEventRead, ...]:
        rows = self._operations.list_business_events(tenant=tenant, operational_day_id=day.id)
        return tuple(_read_event(row, day.business_date) for row in rows)

    def _day_summary(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        day: OperationalDay,
    ) -> FactualMemoryResult:
        events = self._events(tenant, day)
        pending = len(self._operations.list_open_work_items(tenant=tenant, operational_day_id=day.id))
        snapshot = self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
        if day.status is OperationalDayStatus.CLOSED:
            if snapshot is None:
                return self._with_day(
                    tenant,
                    query,
                    day,
                    facts=None,
                    events=(),
                    empty_reason=FactualEmptyReason.NO_COMPLETED_CLOSE,
                )
            facts = DaySummaryFacts(
                day_status=day.status.value,
                sale_count=snapshot.sale_count,
                gross_sales_total=_money(snapshot.gross_sales_total, snapshot.currency),
                cash_sales_total=_money(snapshot.cash_total, snapshot.currency),
                card_sales_total=_money(snapshot.card_total, snapshot.currency),
                transfer_sales_total=_money(snapshot.transfer_total, snapshot.currency),
                expected_cash=_money(snapshot.expected_cash, snapshot.currency),
                counted_cash=_money(snapshot.counted_cash, snapshot.currency),
                cash_difference=_money(snapshot.cash_difference, snapshot.currency),
                cash_status=snapshot.cash_status.value,
                close_status="completed",
                pending_work_count=pending,
                currency=snapshot.currency,
            )
        elif day.status is OperationalDayStatus.OPEN:
            currency = self._currency(tenant)
            totals = self._operations.summarize_day(
                tenant=tenant,
                operational_day_id=day.id,
                currency=currency,
            )
            count = self._operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
            expected = counted = difference = status = None
            if count is not None:
                expected_amount = Decimal(totals.cash_total)
                difference_amount = cash_difference(expected_amount, count.amount)
                expected = _money(expected_amount, currency)
                counted = _money(count.amount, currency)
                difference = _money(difference_amount, currency) if difference_amount is not None else None
                status = cash_status_for(difference_amount).value
            facts = DaySummaryFacts(
                day_status=day.status.value,
                sale_count=totals.sale_count,
                gross_sales_total=totals.gross_sales_total,
                cash_sales_total=totals.cash_total,
                card_sales_total=totals.card_total,
                transfer_sales_total=totals.transfer_total,
                expected_cash=expected,
                counted_cash=counted,
                cash_difference=difference,
                cash_status=status,
                close_status="not_completed",
                pending_work_count=pending,
                currency=totals.currency,
            )
        else:
            raise ValidationAppError("operational day status is not open or closed")
        return self._with_day(tenant, query, day, facts=facts, events=events, empty_reason=None)

    def _day_events(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        day: OperationalDay,
    ) -> FactualMemoryResult:
        events = self._events(tenant, day)
        reason = FactualEmptyReason.NO_MATCHING_FACTS if not events else None
        return self._with_day(tenant, query, day, facts=None, events=events if reason is None else (), empty_reason=reason)

    def _sales_summary(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        day: OperationalDay,
    ) -> FactualMemoryResult:
        events = self._events(tenant, day)
        snapshot = (
            self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
            if day.status is OperationalDayStatus.CLOSED
            else None
        )
        if day.status is OperationalDayStatus.CLOSED and snapshot is None:
            return self._with_day(
                tenant,
                query,
                day,
                facts=None,
                events=(),
                empty_reason=FactualEmptyReason.NO_COMPLETED_CLOSE,
            )
        if snapshot is not None:
            sale_count = snapshot.sale_count
            gross = _money(snapshot.gross_sales_total, snapshot.currency)
            cash = _money(snapshot.cash_total, snapshot.currency)
            card = _money(snapshot.card_total, snapshot.currency)
            transfer = _money(snapshot.transfer_total, snapshot.currency)
            currency = snapshot.currency
        else:
            totals = self._operations.summarize_day(
                tenant=tenant,
                operational_day_id=day.id,
                currency=self._currency(tenant),
            )
            sale_count = totals.sale_count
            gross = totals.gross_sales_total
            cash = totals.cash_total
            card = totals.card_total
            transfer = totals.transfer_total
            currency = totals.currency
        if sale_count == 0:
            return self._with_day(
                tenant,
                query,
                day,
                facts=None,
                events=(),
                empty_reason=FactualEmptyReason.NO_CONFIRMED_SALES,
            )
        refs = tuple(
            SaleEventRef(event_id=event.event_id, sale_session_id=UUID(str(event.facts["sale_session_id"])))
            for event in events
            if event.event_type == BusinessEventType.SALE_CONFIRMED.value and event.facts.get("sale_session_id")
        )
        facts = SalesSummaryFacts(
            sale_count=sale_count,
            gross_sales_total=gross,
            cash_sales_total=cash,
            card_sales_total=card,
            transfer_sales_total=transfer,
            currency=currency,
            sale_event_refs=refs,
        )
        return self._with_day(tenant, query, day, facts=facts, events=(), empty_reason=None)

    def _cash_summary(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        day: OperationalDay,
    ) -> FactualMemoryResult:
        snapshot = self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
        if day.status is OperationalDayStatus.CLOSED and snapshot is not None:
            events = self._events(tenant, day)
            counted_at = _counted_at(events, snapshot.cash_count_id)
            facts = _cash_from_snapshot(snapshot, counted_at)
            return self._with_day(tenant, query, day, facts=facts, events=(), empty_reason=None)
        if day.status is OperationalDayStatus.CLOSED:
            return self._with_day(
                tenant,
                query,
                day,
                facts=None,
                events=(),
                empty_reason=FactualEmptyReason.NO_COMPLETED_CLOSE,
            )
        count = self._operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
        if count is None:
            return self._with_day(
                tenant,
                query,
                day,
                facts=None,
                events=(),
                empty_reason=FactualEmptyReason.NO_CASH_COUNT,
            )
        currency = count.currency
        totals = self._operations.summarize_day(tenant=tenant, operational_day_id=day.id, currency=currency)
        difference = cash_difference(Decimal(totals.cash_total), count.amount)
        facts = CashSummaryFacts(
            expected_cash=totals.cash_total,
            counted_cash=_money(count.amount, currency),
            cash_difference=_money(difference, currency) if difference is not None else "0.00",
            cash_status=cash_status_for(difference).value,
            currency=currency,
            counted_at=count.counted_at,
        )
        return self._with_day(tenant, query, day, facts=facts, events=(), empty_reason=None)

    def _close_summary(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        day: OperationalDay,
    ) -> FactualMemoryResult:
        snapshot = self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
        if snapshot is None:
            return self._with_day(
                tenant,
                query,
                day,
                facts=None,
                events=(),
                empty_reason=FactualEmptyReason.NO_COMPLETED_CLOSE,
            )
        return self._close_result(tenant, query.query_type, day, snapshot, business_date=day.business_date)

    def _latest_close(self, tenant: TenantContext) -> FactualMemoryResult:
        snapshot = self._operations.get_latest_completed_close(tenant=tenant)
        if snapshot is None:
            return FactualMemoryResult(
                query_type=FactualQueryType.LATEST_CLOSE,
                business_id=tenant.business_id,
                business_date=None,
                period_start=None,
                period_end=None,
                facts=None,
                events=(),
                source_coverage=None,
                limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
                empty_reason=FactualEmptyReason.NO_COMPLETED_CLOSE,
            )
        day = self._operations.get_by_date(tenant=tenant, business_date=snapshot.business_date)
        if day is None:
            return FactualMemoryResult(
                query_type=FactualQueryType.LATEST_CLOSE,
                business_id=tenant.business_id,
                business_date=snapshot.business_date,
                period_start=snapshot.business_date,
                period_end=snapshot.business_date,
                facts=_close_facts(snapshot, None),
                events=(),
                source_coverage=None,
                limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
                empty_reason=None,
            )
        query = FactualMemoryQuery(query_type=FactualQueryType.LATEST_CLOSE)
        return self._close_result(tenant, query.query_type, day, snapshot, business_date=snapshot.business_date)

    def _close_result(
        self,
        tenant: TenantContext,
        query_type: FactualQueryType,
        day: OperationalDay,
        snapshot: ClosingSnapshot,
        *,
        business_date: date,
    ) -> FactualMemoryResult:
        outcome = self._operations.get_daily_close_outcome(tenant=tenant, operational_day_id=day.id)
        events = self._events(tenant, day)
        close_events = tuple(
            event for event in events if event.event_type == BusinessEventType.DAILY_CLOSE_COMPLETED.value
            and event.source_entity_id == snapshot.id
        )
        facts = _close_facts(snapshot, None if outcome is None else outcome.status.value)
        return FactualMemoryResult(
            query_type=query_type,
            business_id=tenant.business_id,
            business_date=business_date,
            period_start=business_date,
            period_end=business_date,
            facts=facts,
            events=close_events,
            source_coverage=self._coverage(tenant, day),
            limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
            empty_reason=None,
        )

    def _recent_differences(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        business_today: date,
    ) -> FactualMemoryResult:
        window = recent_days_in_range(query.recent_days)
        period_end = business_today
        period_start = business_today - timedelta(days=window - 1)
        rows = self._operations.list_cash_difference_closes(
            tenant=tenant,
            period_start=period_start,
            period_end=period_end,
        )
        facts = tuple(_difference_fact(row) for row in rows)
        return FactualMemoryResult(
            query_type=FactualQueryType.RECENT_CASH_DIFFERENCES,
            business_id=tenant.business_id,
            business_date=None,
            period_start=period_start,
            period_end=period_end,
            facts=None if not facts else facts,
            events=(),
            source_coverage=None,
            limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
            empty_reason=FactualEmptyReason.NO_MATCHING_FACTS if not facts else None,
        )

    def _with_day(
        self,
        tenant: TenantContext,
        query: FactualMemoryQuery,
        day: OperationalDay,
        *,
        facts: DaySummaryFacts | SalesSummaryFacts | CashSummaryFacts | CloseSummaryFacts | None,
        events: tuple[BusinessEventRead, ...],
        empty_reason: FactualEmptyReason | None,
    ) -> FactualMemoryResult:
        return FactualMemoryResult(
            query_type=query.query_type,
            business_id=tenant.business_id,
            business_date=day.business_date,
            period_start=day.business_date,
            period_end=day.business_date,
            facts=facts,
            events=events,
            source_coverage=self._coverage(tenant, day),
            limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
            empty_reason=empty_reason,
        )


def factual_reply_text(result: FactualMemoryResult) -> str:
    """Server-owned Spanish. Not stored on the result. Amounts come from facts."""
    reason = result.empty_reason
    if reason is FactualEmptyReason.NO_CONFIRMED_SALES or (
        result.query_type is FactualQueryType.SALES_SUMMARY and reason is not None
    ):
        return "No encuentro ventas registradas en Lumo para ese día."
    if reason is FactualEmptyReason.NO_CASH_COUNT:
        return "No encuentro un conteo de efectivo registrado en Lumo para ese día."
    if reason is FactualEmptyReason.NO_COMPLETED_CLOSE:
        if result.query_type is FactualQueryType.LATEST_CLOSE:
            return "No encuentro un cierre registrado en Lumo."
        return "No encuentro un cierre registrado en Lumo para esa fecha."
    if reason is FactualEmptyReason.NO_MATCHING_FACTS:
        if result.query_type is FactualQueryType.RECENT_CASH_DIFFERENCES:
            return "No encuentro un faltante o sobrante registrado en Lumo en esos días."
        return "No encuentro un evento registrado en Lumo para ese día."
    if reason is FactualEmptyReason.NO_OPERATIONAL_DAY:
        if result.query_type is FactualQueryType.SALES_SUMMARY:
            return "No encuentro ventas registradas en Lumo para ese día."
        if result.query_type in {FactualQueryType.CLOSE_SUMMARY, FactualQueryType.CASH_SUMMARY}:
            return "No encuentro un cierre registrado en Lumo para esa fecha." if result.query_type is FactualQueryType.CLOSE_SUMMARY else "No encuentro un conteo de efectivo registrado en Lumo para ese día."
        return "No encuentro un día registrado en Lumo para esa fecha."
    facts = result.facts
    if isinstance(facts, SalesSummaryFacts):
        return (
            "Según las ventas registradas en Lumo, hay "
            f"{facts.sale_count} ventas por {facts.gross_sales_total} {facts.currency}."
        )
    if isinstance(facts, CloseSummaryFacts):
        lead = (
            "El último cierre registrado en Lumo"
            if result.query_type is FactualQueryType.LATEST_CLOSE
            else "El cierre registrado"
        )
        return (
            f"{lead} para {facts.business_date.isoformat()} tiene ventas registradas por "
            f"{facts.gross_sales_total} {facts.currency}. "
            f"Caja: {_cash_label(facts.cash_status)}. Diferencia: {facts.cash_difference}."
        )
    if isinstance(facts, CashSummaryFacts):
        return (
            "En las operaciones registradas en Lumo, el efectivo esperado es "
            f"{facts.expected_cash}, el contado es {facts.counted_cash} y la diferencia es "
            f"{facts.cash_difference} ({_cash_label(facts.cash_status)})."
        )
    if isinstance(facts, tuple):
        lines = [
            f"{item.business_date.isoformat()}: diferencia {item.cash_difference} ({_cash_label(item.cash_status)})"
            for item in facts
        ]
        return "En las operaciones registradas en Lumo, " + "; ".join(lines) + "."
    if isinstance(facts, DaySummaryFacts):
        if facts.sale_count == 0:
            return (
                "En las operaciones registradas en Lumo no encuentro ventas registradas en Lumo "
                f"para ese día. El día está {facts.day_status} y el cierre está {facts.close_status}."
            )
        return (
            "En las operaciones registradas en Lumo hay "
            f"{facts.sale_count} ventas por {facts.gross_sales_total} {facts.currency}."
        )
    return "No encuentro operaciones registradas en Lumo para ese día."


def _cash_label(status: str) -> str:
    if status == CashStatus.BALANCED.value:
        return "Cuadrado"
    if status == CashStatus.SHORT.value:
        return "Faltante"
    if status == CashStatus.OVER.value:
        return "Sobrante"
    return status


def _money(amount: Decimal | str | None, currency: str) -> str:
    if amount is None:
        return "0.00"
    return Money(amount if isinstance(amount, str) else format(amount, "f"), currency).to_json()["amount"]


def _read_event(event: BusinessEvent, business_date: date) -> BusinessEventRead:
    return BusinessEventRead(
        event_id=event.id,
        event_type=event.event_type.value,
        business_date=business_date,
        occurred_at=event.occurred_at,
        source_type=event.source_type.value,
        source_entity_type=event.source_entity_type.value,
        source_entity_id=event.source_entity_id,
        facts=dict(event.facts),
    )


def _counted_at(events: tuple[BusinessEventRead, ...], cash_count_id: UUID) -> datetime | None:
    for event in events:
        if (
            event.event_type == BusinessEventType.CASH_COUNT_RECORDED.value
            and event.source_entity_id == cash_count_id
        ):
            return event.occurred_at
    return None


def _cash_from_snapshot(snapshot: ClosingSnapshot, counted_at: datetime | None) -> CashSummaryFacts:
    return CashSummaryFacts(
        expected_cash=_money(snapshot.expected_cash, snapshot.currency),
        counted_cash=_money(snapshot.counted_cash, snapshot.currency),
        cash_difference=_money(snapshot.cash_difference, snapshot.currency),
        cash_status=snapshot.cash_status.value,
        currency=snapshot.currency,
        counted_at=counted_at,
    )


def _close_facts(snapshot: ClosingSnapshot, outcome_status: str | None) -> CloseSummaryFacts:
    return CloseSummaryFacts(
        business_date=snapshot.business_date,
        closed_at=snapshot.closed_at,
        sale_count=snapshot.sale_count,
        gross_sales_total=_money(snapshot.gross_sales_total, snapshot.currency),
        expected_cash=_money(snapshot.expected_cash, snapshot.currency),
        counted_cash=_money(snapshot.counted_cash, snapshot.currency),
        cash_difference=_money(snapshot.cash_difference, snapshot.currency),
        cash_status=snapshot.cash_status.value,
        outcome_status=outcome_status,
        currency=snapshot.currency,
    )


def _difference_fact(snapshot: ClosingSnapshot) -> CashDifferenceFact:
    return CashDifferenceFact(
        business_date=snapshot.business_date,
        expected_cash=_money(snapshot.expected_cash, snapshot.currency),
        counted_cash=_money(snapshot.counted_cash, snapshot.currency),
        cash_difference=_money(snapshot.cash_difference, snapshot.currency),
        cash_status=snapshot.cash_status.value,
        closed_at=snapshot.closed_at,
        currency=snapshot.currency,
    )


def _timeline_event(row: DatedBusinessEvent) -> dict[str, Any]:
    body = _read_event(row.event, row.business_date).to_dict()
    body["local_time"] = _local_time(row.event.occurred_at, row.timezone_name)
    return body


def _local_time(occurred_at: datetime, timezone_name: str) -> str:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValidationAppError("invalid business timezone") from exc
    return occurred_at.astimezone(zone).strftime("%H:%M")


def _cursor_inside_window(
    occurred_at: datetime,
    *,
    period_start: date,
    period_end: date,
    timezone_name: str,
) -> bool:
    try:
        zone = ZoneInfo(timezone_name)
    except Exception as exc:
        raise ValidationAppError("invalid business timezone") from exc
    start = datetime.combine(period_start, time.min, tzinfo=zone)
    end = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=zone)
    instant = occurred_at.astimezone(UTC)
    return start <= instant < end


def _encode_cursor(row: DatedBusinessEvent) -> str:
    raw = f"{row.event.occurred_at.isoformat()}|{row.event.id}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[datetime, UUID]:
    padded = value + ("=" * (-len(value) % 4))
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        stamp, raw_id = decoded.split("|", 1)
        occurred_at = datetime.fromisoformat(stamp)
        event_id = UUID(raw_id)
    except (ValueError, binascii.Error, UnicodeError) as exc:
        raise ValidationAppError("memory cursor is malformed") from exc
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValidationAppError("memory cursor is malformed")
    return occurred_at, event_id


def prepare_factual_query(
    *,
    query_type: FactualQueryType,
    scope: str,
    business_today: date,
    explicit_date: date | None = None,
    month: int | None = None,
    day: int | None = None,
    recent_days: int | None = None,
) -> FactualMemoryQuery | None:
    """Resolve a phrase scope. None means the tool must not run."""
    if query_type is FactualQueryType.LATEST_CLOSE:
        return FactualMemoryQuery(query_type=query_type)
    if query_type is FactualQueryType.RECENT_CASH_DIFFERENCES:
        return FactualMemoryQuery(query_type=query_type, recent_days=recent_days_in_range(recent_days))
    if scope == "today":
        resolved = business_today
    elif scope == "yesterday":
        resolved = business_today - timedelta(days=1)
    elif scope == "date":
        if explicit_date is not None:
            resolved = explicit_date
        elif month is not None and day is not None:
            try:
                resolved = date(business_today.year, month, day)
            except ValueError:
                return None
        else:
            return None
        if business_date_is_future(resolved, business_today):
            return None
    else:
        return None
    return FactualMemoryQuery(query_type=query_type, business_date=resolved)
