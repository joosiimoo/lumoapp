from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.application.ports import AuditService, IdentityPort
from app.domain.operations import (
    RESPONSIBLE_PARTY_BUSINESS,
    SOURCE_DAILY_CLOSE_RULE,
    CashStatus,
    InvalidBusinessTimezone,
    ResolutionActorType,
    WorkItem,
    WorkItemStatus,
    WorkItemType,
    business_date_for,
    cash_difference,
    cash_status_for,
    desired_open_type,
    priority_for,
    reason_code_for,
    resolution_for,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository

_TWO_PLACES = Decimal("0.01")


def sync_daily_close_work_items(
    *,
    identities: IdentityPort,
    operations: OperationsRepository,
    audit: AuditService,
    tenant: TenantContext,
    now: datetime | None = None,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    closing: bool = False,
    origin: str | None = None,
    omit_actor: bool = False,
) -> int:
    """Reconcile today's Daily Close WorkItems inside the caller's transaction.

    ``closing`` resolves the open row and inserts nothing. A matching open row
    whose evidence is unchanged is not written and is not audited.
    """
    instant = _utc(now)
    business = identities.get_business(tenant)
    try:
        business_date = business_date_for(instant, business.timezone)
    except InvalidBusinessTimezone as exc:
        raise ValidationAppError("invalid business timezone") from exc
    day = operations.lock_day_for_update(tenant=tenant, business_date=business_date)
    if day is None or day.business_date != business_date:
        return 0
    if closing:
        _resolve_open(
            operations=operations,
            audit=audit,
            tenant=tenant,
            operational_day_id=day.id,
            desired=None,
            closing=True,
            resolved_at=instant,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            route_or_tool=route_or_tool,
            omit_actor=omit_actor,
        )
        return 0
    if day.status.value == "closed":
        return 0
    totals = operations.summarize_day(
        tenant=tenant,
        operational_day_id=day.id,
        currency=business.currency,
    )
    count = operations.get_current_cash_count(tenant=tenant, operational_day_id=day.id)
    difference = None if count is None else cash_difference(Decimal(totals.cash_total), count.amount)
    status = cash_status_for(difference)
    desired = desired_open_type(
        day_status=day.status,
        sale_count=totals.sale_count,
        cash_status=status,
    )
    evidence = _evidence(
        currency=business.currency,
        expected_cash=totals.cash_total,
        sale_count=totals.sale_count,
        cash_status=status,
        counted_cash=None if count is None else count.amount,
        cash_difference_amount=difference,
        cash_count_id=None if count is None else count.id,
    )
    reason = reason_code_for(desired, status).value if desired is not None else None
    _resolve_open(
        operations=operations,
        audit=audit,
        tenant=tenant,
        operational_day_id=day.id,
        desired=desired,
        closing=False,
        resolved_at=instant,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        route_or_tool=route_or_tool,
        omit_actor=omit_actor,
    )
    if desired is None or reason is None:
        return 0
    open_rows = operations.list_open_work_items(tenant=tenant, operational_day_id=day.id)
    current = next((row for row in open_rows if row.type is desired), None)
    if current is not None:
        operations.refresh_work_item_evidence(
            tenant=tenant,
            work_item_id=current.id,
            reason_code=reason,
            evidence=evidence,
            updated_at=instant,
        )
        return 0
    created = WorkItem(
        id=new_uuid7(),
        business_id=tenant.business_id,
        operational_day_id=day.id,
        type=desired,
        status=WorkItemStatus.OPEN,
        priority=priority_for(desired),
        responsible_party=RESPONSIBLE_PARTY_BUSINESS,
        reason_code=reason,
        source=SOURCE_DAILY_CLOSE_RULE,
        evidence=evidence,
        created_at=instant,
        updated_at=instant,
    )
    stored = operations.insert_work_item(tenant=tenant, work_item=created)
    _audit_created(
        audit=audit,
        tenant=tenant,
        item=stored,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        route_or_tool=route_or_tool,
        origin=origin,
        omit_actor=omit_actor,
    )
    return 1


def _resolve_open(
    *,
    operations: OperationsRepository,
    audit: AuditService,
    tenant: TenantContext,
    operational_day_id: UUID,
    desired: WorkItemType | None,
    closing: bool,
    resolved_at: datetime,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    omit_actor: bool,
) -> None:
    for item in operations.list_open_work_items(tenant=tenant, operational_day_id=operational_day_id):
        if not closing and item.type is desired:
            continue
        verdict = resolution_for(open_type=item.type, desired_type=desired, closing=closing)
        if verdict is None:
            continue
        code, actor_type = verdict
        actor_id = tenant.actor_id if actor_type is ResolutionActorType.BUSINESS else None
        resolved = operations.resolve_work_item(
            tenant=tenant,
            work_item_id=item.id,
            resolved_at=resolved_at,
            resolution_actor_type=actor_type,
            resolved_by_actor_id=actor_id,
            resolution_code=code,
        )
        _audit_resolved(
            audit=audit,
            tenant=tenant,
            item=resolved,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            route_or_tool=route_or_tool,
            omit_actor=omit_actor or actor_type is ResolutionActorType.SYSTEM,
        )


def _evidence(
    *,
    currency: str,
    expected_cash: str,
    sale_count: int,
    cash_status: CashStatus,
    counted_cash: Decimal | None,
    cash_difference_amount: Decimal | None,
    cash_count_id: UUID | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "currency": currency,
        "expected_cash": _decimal_string(expected_cash),
        "sale_count": sale_count,
        "cash_status": cash_status.value,
    }
    if counted_cash is None:
        return payload
    payload["counted_cash"] = _decimal_string(counted_cash)
    payload["cash_difference"] = _decimal_string(cash_difference_amount or Decimal("0"))
    payload["cash_count_id"] = str(cash_count_id)
    return payload


def _audit_created(
    *,
    audit: AuditService,
    tenant: TenantContext,
    item: WorkItem,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    origin: str | None,
    omit_actor: bool,
) -> None:
    after = _identity_payload(item)
    if origin is not None:
        after["origin"] = origin
    audit.record(
        tenant=tenant,
        action="work_item.created",
        route_or_tool=route_or_tool,
        result="created",
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        after_payload=after,
        omit_actor=omit_actor,
    )


def _audit_resolved(
    *,
    audit: AuditService,
    tenant: TenantContext,
    item: WorkItem,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
    omit_actor: bool,
) -> None:
    after = _identity_payload(item)
    after["resolution_code"] = item.resolution_code.value if item.resolution_code is not None else None
    after["resolution_actor_type"] = (
        item.resolution_actor_type.value if item.resolution_actor_type is not None else None
    )
    if item.resolution_actor_type is ResolutionActorType.BUSINESS and item.resolved_by_actor_id is not None:
        after["resolved_by_actor_id"] = str(item.resolved_by_actor_id)
    audit.record(
        tenant=tenant,
        action="work_item.resolved",
        route_or_tool=route_or_tool,
        result="resolved",
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        after_payload=after,
        omit_actor=omit_actor,
    )


def _identity_payload(item: WorkItem) -> dict[str, Any]:
    return {
        "work_item_id": str(item.id),
        "operational_day_id": str(item.operational_day_id),
        "type": item.type.value,
        "status": item.status.value,
        "reason_code": item.reason_code,
        "evidence": dict(item.evidence),
    }


def _decimal_string(value: Decimal | str) -> str:
    amount = value if isinstance(value, Decimal) else Decimal(value)
    return format(amount.quantize(_TWO_PLACES), "f")


def _utc(value: datetime | None) -> datetime:
    instant = value if value is not None else utcnow()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValidationAppError("clock must be timezone-aware UTC")
    return instant.astimezone(UTC)
