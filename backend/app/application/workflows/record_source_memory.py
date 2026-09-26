from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.application.ports import IdentityPort
from app.domain.operations import (
    LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
    BusinessEvent,
    BusinessEventSourceType,
    BusinessEventType,
    CoverageDomain,
    CoverageSourceType,
    CoverageStatus,
    InvalidBusinessTimezone,
    OperationalDayStatus,
    SourceCoverageRecord,
    SourceEntityType,
    business_date_for,
    cash_difference,
    cash_status_for,
)
from app.domain.operations.business_event import (
    cash_count_recorded_facts,
    daily_close_completed_facts,
    sale_confirmed_facts,
)
from app.domain.operations.closing_snapshot import ClosingSnapshot
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository


def record_confirmed_sale(
    *,
    operations: OperationsRepository,
    tenant: TenantContext,
    operational_day_id: UUID,
    sale_session_id: UUID,
    payment_id: UUID,
    payment_method: str,
    amount: Decimal | str,
    currency: str,
    occurred_at: datetime | None,
    created_at: datetime,
) -> None:
    if occurred_at is None:
        raise ValidationAppError("sale_confirmed requires SaleSession.confirmed_at")
    _ensure_observed_coverage(
        operations=operations,
        tenant=tenant,
        operational_day_id=operational_day_id,
        domain=CoverageDomain.SALES,
        created_at=created_at,
    )
    operations.append_business_event(
        tenant=tenant,
        event=BusinessEvent(
            id=new_uuid7(),
            business_id=tenant.business_id,
            operational_day_id=operational_day_id,
            event_type=BusinessEventType.SALE_CONFIRMED,
            occurred_at=occurred_at,
            source_type=BusinessEventSourceType.MANUAL_CAPTURE,
            source_entity_type=SourceEntityType.SALE_SESSION,
            source_entity_id=sale_session_id,
            facts=sale_confirmed_facts(
                sale_session_id=sale_session_id,
                payment_id=payment_id,
                payment_method=payment_method,
                amount=amount,
                currency=currency,
            ),
            created_at=created_at,
        ),
    )


def record_cash_count(
    *,
    operations: OperationsRepository,
    tenant: TenantContext,
    operational_day_id: UUID,
    cash_count_id: UUID,
    expected_cash: Decimal | str,
    counted_cash: Decimal | str,
    currency: str,
    occurred_at: datetime,
    created_at: datetime,
) -> None:
    difference = cash_difference(expected_cash, counted_cash)
    if difference is None:
        raise ValidationAppError("cash_count_recorded requires a counted amount")
    _ensure_observed_coverage(
        operations=operations,
        tenant=tenant,
        operational_day_id=operational_day_id,
        domain=CoverageDomain.CASH_COUNT,
        created_at=created_at,
    )
    operations.append_business_event(
        tenant=tenant,
        event=BusinessEvent(
            id=new_uuid7(),
            business_id=tenant.business_id,
            operational_day_id=operational_day_id,
            event_type=BusinessEventType.CASH_COUNT_RECORDED,
            occurred_at=occurred_at,
            source_type=BusinessEventSourceType.MANUAL_CAPTURE,
            source_entity_type=SourceEntityType.CASH_COUNT,
            source_entity_id=cash_count_id,
            facts=cash_count_recorded_facts(
                cash_count_id=cash_count_id,
                expected_cash=expected_cash,
                counted_cash=counted_cash,
                cash_difference_amount=difference,
                cash_status=cash_status_for(difference).value,
                currency=currency,
            ),
            created_at=created_at,
        ),
    )


def record_daily_close(
    *,
    operations: OperationsRepository,
    tenant: TenantContext,
    snapshot: ClosingSnapshot,
    outcome_run_id: UUID,
    created_at: datetime,
) -> None:
    if snapshot.sale_count >= 1:
        _ensure_observed_coverage(
            operations=operations,
            tenant=tenant,
            operational_day_id=snapshot.operational_day_id,
            domain=CoverageDomain.SALES,
            created_at=created_at,
        )
    current = operations.get_current_cash_count(
        tenant=tenant,
        operational_day_id=snapshot.operational_day_id,
    )
    if current is not None:
        _ensure_observed_coverage(
            operations=operations,
            tenant=tenant,
            operational_day_id=snapshot.operational_day_id,
            domain=CoverageDomain.CASH_COUNT,
            created_at=created_at,
        )
    operations.append_business_event(
        tenant=tenant,
        event=BusinessEvent(
            id=new_uuid7(),
            business_id=tenant.business_id,
            operational_day_id=snapshot.operational_day_id,
            event_type=BusinessEventType.DAILY_CLOSE_COMPLETED,
            occurred_at=snapshot.closed_at,
            source_type=BusinessEventSourceType.MANUAL_CAPTURE,
            source_entity_type=SourceEntityType.CLOSING_SNAPSHOT,
            source_entity_id=snapshot.id,
            facts=daily_close_completed_facts(
                outcome_run_id=outcome_run_id,
                closing_snapshot_id=snapshot.id,
                sale_count=snapshot.sale_count,
                gross_sales_total=snapshot.gross_sales_total,
                expected_cash=snapshot.expected_cash,
                counted_cash=snapshot.counted_cash,
                cash_difference_amount=snapshot.cash_difference,
                cash_status=snapshot.cash_status.value,
                currency=snapshot.currency,
            ),
            created_at=created_at,
        ),
    )


def ensure_recorded_coverage_for_open_today(
    *,
    identities: IdentityPort,
    operations: OperationsRepository,
    tenant: TenantContext,
    now: datetime | None,
) -> None:
    """Ensure coverage for the open day dated today. Does not append events."""
    instant = now if now is not None else utcnow()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationAppError("coverage initializer requires a timezone-aware instant")
    instant = instant.astimezone(UTC)
    business = identities.get_business(tenant)
    try:
        business_date = business_date_for(instant, business.timezone)
    except InvalidBusinessTimezone as exc:
        raise ValidationAppError("invalid business timezone") from exc
    day = operations.get_by_date(tenant=tenant, business_date=business_date)
    if day is None or day.status is not OperationalDayStatus.OPEN or day.business_date != business_date:
        return
    totals = operations.summarize_day(
        tenant=tenant,
        operational_day_id=day.id,
        currency=business.currency,
    )
    if totals.sale_count >= 1:
        _ensure_observed_coverage(
            operations=operations,
            tenant=tenant,
            operational_day_id=day.id,
            domain=CoverageDomain.SALES,
            created_at=instant,
        )
    if operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id) is not None:
        _ensure_observed_coverage(
            operations=operations,
            tenant=tenant,
            operational_day_id=day.id,
            domain=CoverageDomain.CASH_COUNT,
            created_at=instant,
        )


def _ensure_observed_coverage(
    *,
    operations: OperationsRepository,
    tenant: TenantContext,
    operational_day_id: UUID,
    domain: CoverageDomain,
    created_at: datetime,
) -> None:
    operations.insert_source_coverage_if_absent(
        tenant=tenant,
        record=SourceCoverageRecord(
            id=new_uuid7(),
            business_id=tenant.business_id,
            operational_day_id=operational_day_id,
            domain=domain,
            source_type=CoverageSourceType.MANUAL_CAPTURE,
            status=CoverageStatus.OBSERVED,
            limitation_code=LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
            created_at=created_at,
        ),
    )
