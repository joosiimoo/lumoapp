"""Read-only Business Stream for the business-local today. Never writes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.workflows.get_daily_close_preparation import business_date_now
from app.domain.operations.business_stream import (
    OperatorState,
    coverage_claim,
    primary_action,
    scripted_copy,
    select_business_stream_state,
)
from app.domain.operations.cash_count import cash_difference, cash_status_for
from app.domain.operations.day import DaySummaryTotals, OperationalDay, OperationalDayStatus
from app.domain.operations.work_item import desired_open_type
from app.domain.shared.money import Money
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository


class GetBusinessStream:
    def __init__(self, identities: IdentityRepository, operations: OperationsRepository) -> None:
        self._identities = identities
        self._operations = operations

    def execute(self, *, tenant: TenantContext, now: datetime | None = None) -> dict[str, Any]:
        business = self._identities.get_business(tenant)
        instant, business_date = business_date_now(timezone_name=business.timezone, now=now)
        day = self._operations.get_by_date(tenant=tenant, business_date=business_date)
        as_of = instant.isoformat()
        if day is None:
            return _envelope(
                business_date=business_date.isoformat(),
                state=OperatorState.NO_ACTIVE_DAY,
                progress="none",
                copy=scripted_copy(state=OperatorState.NO_ACTIVE_DAY, expected_cash_text=None),
                factual_summary=None,
                attention=None,
                action=None,
                coverage=None,
                as_of=as_of,
            )

        if day.status is OperationalDayStatus.CLOSED:
            snapshot = self._operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id)
            if snapshot is None:
                return _envelope(
                    business_date=business_date.isoformat(),
                    state=OperatorState.UNAVAILABLE,
                    progress=None,
                    copy=scripted_copy(state=OperatorState.UNAVAILABLE, expected_cash_text=None),
                    factual_summary=None,
                    attention=None,
                    action=None,
                    coverage=None,
                    as_of=as_of,
                )
            self._read_existing_rows(tenant=tenant, day=day)
            copy = scripted_copy(state=OperatorState.CLOSED, expected_cash_text=None)
            currency = snapshot.currency
            return _envelope(
                business_date=business_date.isoformat(),
                state=OperatorState.CLOSED,
                progress="completed",
                copy=copy,
                factual_summary={
                    "basis": "closing_snapshot",
                    "sale_count": snapshot.sale_count,
                    "gross_sales_total": _money(snapshot.gross_sales_total, currency),
                    "cash_total": _money(snapshot.cash_total, currency),
                    "card_total": _money(snapshot.card_total, currency),
                    "transfer_total": _money(snapshot.transfer_total, currency),
                    "expected_cash": _money(snapshot.expected_cash, currency),
                    "counted_cash": _money(snapshot.counted_cash, currency),
                    "cash_difference": _money(snapshot.cash_difference, currency),
                    "cash_status": snapshot.cash_status.value,
                    "closed_at": snapshot.closed_at.isoformat(),
                },
                attention=None,
                action=None,
                coverage=coverage_claim(),
                as_of=as_of,
            )

        totals = self._operations.summarize_day(
            tenant=tenant,
            operational_day_id=day.id,
            currency=business.currency,
        )
        count = self._operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
        difference = cash_difference(Decimal(totals.cash_total), None if count is None else count.amount)
        cash_status = cash_status_for(difference)
        desired = desired_open_type(
            day_status=day.status,
            sale_count=totals.sale_count,
            cash_status=None if count is None else cash_status,
        )
        state, progress = select_business_stream_state(
            day_status=day.status,
            desired_type=desired,
            has_snapshot=False,
        )
        work_item_id, outcome_run_id = self._existing_ids(tenant=tenant, day=day, desired=desired)
        expected_text = _amount_text(totals.cash_total) if state is OperatorState.CASH_COUNT_REQUIRED else None
        copy = scripted_copy(state=state, expected_cash_text=expected_text)
        action = primary_action(state=state, work_item_id=work_item_id, outcome_run_id=outcome_run_id)
        attention = None if copy.why is None else {"why": copy.why}
        return _envelope(
            business_date=business_date.isoformat(),
            state=state,
            progress=None if progress is None else progress.value,
            copy=copy,
            factual_summary=_open_summary(totals, count_amount=None if count is None else count.amount, difference=difference, cash_status=cash_status.value if count is not None else "not_counted"),
            attention=attention,
            action=action,
            coverage=None if state is OperatorState.UNAVAILABLE else coverage_claim(),
            as_of=as_of,
        )

    def _read_existing_rows(self, *, tenant: TenantContext, day: OperationalDay) -> None:
        self._operations.list_open_work_items(tenant=tenant, operational_day_id=day.id)
        self._operations.get_daily_close_outcome(tenant=tenant, operational_day_id=day.id)
        self._operations.list_source_coverage(tenant=tenant, operational_day_id=day.id)

    def _existing_ids(self, *, tenant: TenantContext, day: OperationalDay, desired) -> tuple[UUID | None, UUID | None]:
        self._operations.list_source_coverage(tenant=tenant, operational_day_id=day.id)
        open_items = self._operations.list_open_work_items(tenant=tenant, operational_day_id=day.id)
        outcome = self._operations.get_daily_close_outcome(tenant=tenant, operational_day_id=day.id)
        match = next((item for item in open_items if item.type is desired), None) if desired is not None else None
        return (None if match is None else match.id, None if outcome is None else outcome.id)


def _open_summary(
    totals: DaySummaryTotals,
    *,
    count_amount: Decimal | None,
    difference: Decimal | None,
    cash_status: str,
) -> dict[str, Any]:
    currency = totals.currency
    counted = None if count_amount is None else _money(count_amount, currency)
    gap = None if difference is None else _money(difference, currency)
    return {
        "basis": "registered_sales",
        "sale_count": totals.sale_count,
        "gross_sales_total": _money(totals.gross_sales_total, currency),
        "cash_total": _money(totals.cash_total, currency),
        "card_total": _money(totals.card_total, currency),
        "transfer_total": _money(totals.transfer_total, currency),
        "expected_cash": _money(totals.cash_total, currency),
        "counted_cash": counted,
        "cash_difference": gap,
        "cash_status": cash_status,
        "closed_at": None,
    }


def _envelope(
    *,
    business_date: str,
    state: OperatorState,
    progress: str | None,
    copy,
    factual_summary: dict[str, Any] | None,
    attention: dict[str, str] | None,
    action: dict[str, Any] | None,
    coverage: dict[str, str] | None,
    as_of: str,
) -> dict[str, Any]:
    return {
        "business_date": business_date,
        "operator_state": state.value,
        "close_progress": progress,
        "responsibility": copy.responsibility,
        "detail": copy.detail,
        "factual_summary": factual_summary,
        "attention": attention,
        "primary_action": action,
        "coverage": coverage,
        "as_of": as_of,
    }


def _money(amount: Decimal | str, currency: str) -> dict[str, str]:
    return Money(amount, currency).to_json()


def _amount_text(amount: Decimal | str) -> str:
    quantized = Decimal(str(amount)).quantize(Decimal("0.01"))
    if quantized < 0:
        return f"-${abs(quantized):.2f}"
    return f"${quantized:.2f}"
