from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.application.ports import AuditService, IdentityPort
from app.application.workflows.sync_daily_close_work_items import sync_daily_close_work_items
from app.domain.operations import (
    OUTCOME_TYPE_DAILY_CLOSE_READY,
    OUTCOME_VERSION,
    OWNER_TYPE_BUSINESS,
    CashStatus,
    InvalidBusinessTimezone,
    OperationalDayStatus,
    OutcomeRun,
    OutcomeRunStatus,
    business_date_for,
    cash_difference,
    cash_status_for,
    derive_daily_close_outcome,
    outcome_evidence,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository


def maintain_open_daily_close(
    *,
    identities: IdentityPort,
    operations: OperationsRepository,
    audit: AuditService,
    tenant: TenantContext,
    now: datetime | None = None,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    origin: str | None = None,
    omit_actor: bool = False,
    outcome_route_or_tool: str | None = None,
) -> int:
    """Ensure today's open-day OutcomeRun, then sync and link WorkItems.

    Used by sale commit, a new cash count, and the today-only initializer.
    Close uses the explicit snapshot → resolve → complete → link order instead.
    """
    run = sync_daily_close_outcome(
        identities=identities,
        operations=operations,
        audit=audit,
        tenant=tenant,
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        route_or_tool=outcome_route_or_tool or route_or_tool,
        origin=origin,
        omit_actor=omit_actor,
        closing=False,
    )
    inserted = sync_daily_close_work_items(
        identities=identities,
        operations=operations,
        audit=audit,
        tenant=tenant,
        now=now,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        route_or_tool=route_or_tool,
        closing=False,
        origin=origin,
        omit_actor=omit_actor,
        outcome_run_id=None if run is None else run.id,
    )
    if run is not None:
        operations.link_null_work_items(
            tenant=tenant,
            operational_day_id=run.operational_day_id,
            outcome_run_id=run.id,
        )
    return inserted


def sync_daily_close_outcome(
    *,
    identities: IdentityPort,
    operations: OperationsRepository,
    audit: AuditService,
    tenant: TenantContext,
    now: datetime | None = None,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    origin: str | None = None,
    omit_actor: bool = False,
    closing: bool = False,
) -> OutcomeRun | None:
    """Recompute the Daily Close OutcomeRun inside the caller's transaction.

    Unchanged status, reason, and evidence are not written. Evidence-only
    changes bump ``updated_at`` and do not audit. A completed row is frozen.
    """
    instant = _utc(now)
    business = identities.get_business(tenant)
    try:
        business_date = business_date_for(instant, business.timezone)
    except InvalidBusinessTimezone as exc:
        raise ValidationAppError("invalid business timezone") from exc
    day = operations.lock_day_for_update(tenant=tenant, business_date=business_date)
    if day is None or day.business_date != business_date:
        return None
    if day.status is OperationalDayStatus.CLOSED and not closing:
        return None
    totals = operations.summarize_day(
        tenant=tenant,
        operational_day_id=day.id,
        currency=business.currency,
    )
    count = operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
    snapshot = (
        operations.get_snapshot_for_day(tenant=tenant, operational_day_id=day.id) if closing else None
    )
    difference = None if count is None else cash_difference(Decimal(totals.cash_total), count.amount)
    cash_status = cash_status_for(difference)
    verdict = derive_daily_close_outcome(
        day_status=day.status,
        sale_count=totals.sale_count,
        cash_status=cash_status,
        has_snapshot=snapshot is not None,
    )
    if verdict is None:
        return None
    evidence = outcome_evidence(
        currency=business.currency,
        sale_count=totals.sale_count,
        gross_sales_total=totals.gross_sales_total,
        expected_cash=totals.cash_total,
        cash_status=cash_status if cash_status is not None else CashStatus.NOT_COUNTED,
        counted_cash=None if count is None else count.amount,
        cash_difference_amount=difference,
        current_cash_count_id=None if count is None else count.id,
    )
    existing = operations.get_daily_close_outcome(tenant=tenant, operational_day_id=day.id)
    if existing is not None and existing.status is OutcomeRunStatus.COMPLETED:
        return existing
    if (
        existing is not None
        and existing.status is OutcomeRunStatus.READY
        and verdict.status is OutcomeRunStatus.IN_PROGRESS
    ):
        return existing
    if existing is None:
        ready_at = instant if verdict.status is not OutcomeRunStatus.IN_PROGRESS else None
        completed_at = instant if verdict.status is OutcomeRunStatus.COMPLETED else None
        snapshot_id = snapshot.id if verdict.status is OutcomeRunStatus.COMPLETED and snapshot is not None else None
        created = OutcomeRun(
            id=new_uuid7(),
            business_id=tenant.business_id,
            operational_day_id=day.id,
            outcome_type=OUTCOME_TYPE_DAILY_CLOSE_READY,
            outcome_version=OUTCOME_VERSION,
            status=verdict.status,
            owner_type=OWNER_TYPE_BUSINESS,
            reason_code=verdict.reason_code.value,
            evidence=evidence,
            created_at=instant,
            updated_at=instant,
            ready_at=ready_at,
            completed_at=completed_at,
            closing_snapshot_id=snapshot_id,
        )
        stored = operations.insert_daily_close_outcome(tenant=tenant, outcome=created)
        _audit_created(
            audit=audit,
            tenant=tenant,
            outcome=stored,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            route_or_tool=route_or_tool,
            origin=origin,
            omit_actor=omit_actor,
        )
        return stored
    same_status = existing.status is verdict.status
    same_reason = existing.reason_code == verdict.reason_code.value
    if same_status and same_reason and dict(existing.evidence) == evidence:
        return existing
    if same_status and same_reason:
        return operations.update_daily_close_outcome_evidence(
            tenant=tenant,
            outcome_run_id=existing.id,
            evidence=evidence,
            updated_at=instant,
        )
    ready_at = existing.ready_at
    completed_at = existing.completed_at
    snapshot_id = existing.closing_snapshot_id
    if verdict.status is OutcomeRunStatus.READY and ready_at is None:
        ready_at = instant
    if verdict.status is OutcomeRunStatus.COMPLETED:
        completed_at = instant
        if ready_at is None:
            ready_at = instant
        if snapshot is None:
            raise ValidationAppError("a completed daily close outcome requires a snapshot")
        snapshot_id = snapshot.id
    updated = operations.update_daily_close_outcome_status(
        tenant=tenant,
        outcome_run_id=existing.id,
        status=verdict.status,
        reason_code=verdict.reason_code.value,
        evidence=evidence,
        ready_at=ready_at,
        completed_at=completed_at,
        closing_snapshot_id=snapshot_id,
        updated_at=instant,
    )
    _audit_status_changed(
        audit=audit,
        tenant=tenant,
        previous=existing,
        outcome=updated,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        route_or_tool=route_or_tool,
        omit_actor=omit_actor,
    )
    return updated


def _audit_created(
    *,
    audit: AuditService,
    tenant: TenantContext,
    outcome: OutcomeRun,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    origin: str | None,
    omit_actor: bool,
) -> None:
    after = _identity_payload(outcome)
    if outcome.closing_snapshot_id is not None:
        after["closing_snapshot_id"] = str(outcome.closing_snapshot_id)
    if origin is not None:
        after["origin"] = origin
    audit.record(
        tenant=tenant,
        action="outcome_run.created",
        route_or_tool=route_or_tool,
        result="created",
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        after_payload=after,
        omit_actor=omit_actor,
    )


def _audit_status_changed(
    *,
    audit: AuditService,
    tenant: TenantContext,
    previous: OutcomeRun,
    outcome: OutcomeRun,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    omit_actor: bool,
) -> None:
    after: dict[str, Any] = {
        "outcome_run_id": str(outcome.id),
        "operational_day_id": str(outcome.operational_day_id),
        "previous_status": previous.status.value,
        "status": outcome.status.value,
        "previous_reason_code": previous.reason_code,
        "reason_code": outcome.reason_code,
        "evidence": dict(outcome.evidence),
    }
    if outcome.status is OutcomeRunStatus.COMPLETED and outcome.closing_snapshot_id is not None:
        after["closing_snapshot_id"] = str(outcome.closing_snapshot_id)
    audit.record(
        tenant=tenant,
        action="outcome_run.status_changed",
        route_or_tool=route_or_tool,
        result="status_changed",
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        after_payload=after,
        omit_actor=omit_actor,
    )


def _identity_payload(outcome: OutcomeRun) -> dict[str, Any]:
    return {
        "outcome_run_id": str(outcome.id),
        "operational_day_id": str(outcome.operational_day_id),
        "outcome_type": outcome.outcome_type,
        "outcome_version": outcome.outcome_version,
        "status": outcome.status.value,
        "reason_code": outcome.reason_code,
        "owner_type": outcome.owner_type,
        "evidence": dict(outcome.evidence),
    }


def _utc(value: datetime | None) -> datetime:
    instant = value if value is not None else utcnow()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationAppError("clock must be timezone-aware UTC")
    return instant.astimezone(UTC)
