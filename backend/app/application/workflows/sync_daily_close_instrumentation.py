from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from app.application.ports import AuditService
from app.domain.operations import OutcomeRun, WorkItemType
from app.domain.operations.work_absorption import (
    EvidenceKind,
    TaskType,
    WorkAbsorptionRecord,
    evidence_ref,
)
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.operations import OperationsRepository

_CLOSE_TASKS = (
    TaskType.ORGANIZE_REGISTERED_SALES,
    TaskType.CALCULATE_EXPECTED_CASH,
    TaskType.RECORD_CASH_COUNT,
    TaskType.RECONCILE_CASH,
    TaskType.PREPARE_CLOSE,
    TaskType.CONFIRM_CLOSE,
)
_SALE_TASKS = (TaskType.ORGANIZE_REGISTERED_SALES, TaskType.CALCULATE_EXPECTED_CASH)
_CASH_TASKS = (TaskType.RECORD_CASH_COUNT, TaskType.RECONCILE_CASH)
_CLOSE_ONLY_TASKS = (TaskType.PREPARE_CLOSE, TaskType.CONFIRM_CLOSE)

_WORK_ITEM_FOR_TASK: dict[TaskType, WorkItemType] = {
    TaskType.RECORD_CASH_COUNT: WorkItemType.CASH_COUNT_REQUIRED,
    TaskType.RECONCILE_CASH: WorkItemType.CASH_DIFFERENCE_REVIEW,
    TaskType.CONFIRM_CLOSE: WorkItemType.CLOSE_CONFIRMATION_REQUIRED,
}


def maintain_daily_close_instrumentation(
    *,
    operations: OperationsRepository,
    audit: AuditService,
    tenant: TenantContext,
    outcome_run: OutcomeRun,
    now: datetime,
    correlation_id: str,
    route_or_tool: str,
    idempotency_key: str | None = None,
    finalize_close: bool = False,
    cash_count_id: UUID | None = None,
    closing_snapshot_id: UUID | None = None,
) -> None:
    """Upsert absorption rows and ensure OutcomeCost inside the caller transaction."""
    if outcome_run.status.value == "completed":
        return
    operations.ensure_outcome_cost_for_run(
        tenant=tenant,
        outcome_run_id=outcome_run.id,
        now=now,
        audit=audit,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        route_or_tool=route_or_tool,
    )
    work_items = operations.list_work_items(tenant=tenant, operational_day_id=outcome_run.operational_day_id)
    work_item_by_type = {item.type: item for item in work_items}

    task_types: tuple[TaskType, ...] = _SALE_TASKS
    if cash_count_id is not None:
        task_types = task_types + _CASH_TASKS
    if finalize_close:
        task_types = _CLOSE_TASKS

    for task_type in task_types:
        evidence = _evidence_for_task(
            outcome_run_id=outcome_run.id,
            task_type=task_type,
            cash_count_id=cash_count_id,
            closing_snapshot_id=closing_snapshot_id,
        )
        work_item_id = None
        mapped = _WORK_ITEM_FOR_TASK.get(task_type)
        if mapped is not None:
            item = work_item_by_type.get(mapped)
            work_item_id = item.id if item is not None else None
        inserted, record = operations.upsert_work_absorption_record(
            tenant=tenant,
            outcome_run_id=outcome_run.id,
            task_type=task_type.value,
            work_item_id=work_item_id,
            evidence_ids=evidence,
            now=now,
        )
        if inserted:
            _audit_absorption_created(
                audit=audit,
                tenant=tenant,
                record=record,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                route_or_tool=route_or_tool,
            )


def _evidence_for_task(
    *,
    outcome_run_id: UUID,
    task_type: TaskType,
    cash_count_id: UUID | None,
    closing_snapshot_id: UUID | None,
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = [evidence_ref(EvidenceKind.OUTCOME_RUN, outcome_run_id)]
    if task_type in _CASH_TASKS and cash_count_id is not None:
        refs.append(evidence_ref(EvidenceKind.CASH_COUNT, cash_count_id))
    if task_type in _CLOSE_ONLY_TASKS and closing_snapshot_id is not None:
        refs.append(evidence_ref(EvidenceKind.CLOSING_SNAPSHOT, closing_snapshot_id))
    if task_type is TaskType.CONFIRM_CLOSE and closing_snapshot_id is not None:
        if not any(r["kind"] == EvidenceKind.CLOSING_SNAPSHOT.value for r in refs):
            refs.append(evidence_ref(EvidenceKind.CLOSING_SNAPSHOT, closing_snapshot_id))
    return refs


def _audit_absorption_created(
    *,
    audit: AuditService,
    tenant: TenantContext,
    record: WorkAbsorptionRecord,
    correlation_id: str,
    idempotency_key: str | None,
    route_or_tool: str,
) -> None:
    audit.record(
        tenant=tenant,
        action="work_absorption.created",
        route_or_tool=route_or_tool,
        result="created",
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        after_payload=_absorption_audit_payload(record),
    )


def _absorption_audit_payload(record: WorkAbsorptionRecord) -> dict[str, Any]:
    return {
        "work_absorption_id": str(record.id),
        "outcome_run_id": str(record.outcome_run_id),
        "task_type": record.task_type.value,
        "baseline_version": record.baseline_version,
        "automation_level": record.automation_level.value,
    }
