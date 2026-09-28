from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

BASELINE_VERSION = "daily_close_ready@1/work_absorption_baseline@1"
MINUTES_PER_ELIMINATED_STEP = 2


class ExecutionMode(StrEnum):
    MANUAL_BY_BUSINESS = "manual_by_business"
    ASSISTED_BY_LUMO = "assisted_by_lumo"
    PREPARED_BY_LUMO = "prepared_by_lumo"
    EXECUTED_WITH_CONFIRMATION = "executed_with_confirmation"
    EXECUTED_AND_REVERSIBLE = "executed_and_reversible"
    EXECUTED_UNDER_POLICY = "executed_under_policy"
    REVIEWED_BY_LUMO_OPERATOR = "reviewed_by_lumo_operator"
    FULLY_AUTOMATED = "fully_automated"


class AutomationLevel(StrEnum):
    MANUAL = "manual"
    ASSISTED = "assisted"
    AUTOMATED = "automated"


class TaskType(StrEnum):
    ORGANIZE_REGISTERED_SALES = "organize_registered_sales"
    CALCULATE_EXPECTED_CASH = "calculate_expected_cash"
    RECORD_CASH_COUNT = "record_cash_count"
    RECONCILE_CASH = "reconcile_cash"
    PREPARE_CLOSE = "prepare_close"
    CONFIRM_CLOSE = "confirm_close"


class EvidenceKind(StrEnum):
    OUTCOME_RUN = "outcome_run"
    WORK_ITEM = "work_item"
    CASH_COUNT = "cash_count"
    CLOSING_SNAPSHOT = "closing_snapshot"
    BUSINESS_EVENT = "business_event"
    SOURCE_COVERAGE = "source_coverage"


@dataclass(frozen=True, slots=True)
class BaselineTaskSpec:
    task_type: TaskType
    human_steps_before: int
    human_steps_after: int
    current_execution_mode: ExecutionMode

    @property
    def previous_execution_mode(self) -> ExecutionMode:
        return ExecutionMode.MANUAL_BY_BUSINESS

    @property
    def estimated_minutes_saved(self) -> int:
        return (self.human_steps_before - self.human_steps_after) * MINUTES_PER_ELIMINATED_STEP


BASELINE_V1: dict[TaskType, BaselineTaskSpec] = {
    TaskType.ORGANIZE_REGISTERED_SALES: BaselineTaskSpec(
        TaskType.ORGANIZE_REGISTERED_SALES, 1, 0, ExecutionMode.FULLY_AUTOMATED
    ),
    TaskType.CALCULATE_EXPECTED_CASH: BaselineTaskSpec(
        TaskType.CALCULATE_EXPECTED_CASH, 1, 0, ExecutionMode.FULLY_AUTOMATED
    ),
    TaskType.RECORD_CASH_COUNT: BaselineTaskSpec(
        TaskType.RECORD_CASH_COUNT, 1, 1, ExecutionMode.EXECUTED_WITH_CONFIRMATION
    ),
    TaskType.RECONCILE_CASH: BaselineTaskSpec(
        TaskType.RECONCILE_CASH, 1, 0, ExecutionMode.PREPARED_BY_LUMO
    ),
    TaskType.PREPARE_CLOSE: BaselineTaskSpec(
        TaskType.PREPARE_CLOSE, 1, 0, ExecutionMode.PREPARED_BY_LUMO
    ),
    TaskType.CONFIRM_CLOSE: BaselineTaskSpec(
        TaskType.CONFIRM_CLOSE, 1, 1, ExecutionMode.EXECUTED_WITH_CONFIRMATION
    ),
}

ALL_TASK_TYPES = tuple(BASELINE_V1.keys())


def automation_level_for(mode: ExecutionMode) -> AutomationLevel:
    if mode is ExecutionMode.MANUAL_BY_BUSINESS:
        return AutomationLevel.MANUAL
    if mode in {
        ExecutionMode.ASSISTED_BY_LUMO,
        ExecutionMode.PREPARED_BY_LUMO,
        ExecutionMode.EXECUTED_WITH_CONFIRMATION,
        ExecutionMode.REVIEWED_BY_LUMO_OPERATOR,
    }:
        return AutomationLevel.ASSISTED
    return AutomationLevel.AUTOMATED


def evidence_ref(kind: EvidenceKind, entity_id: UUID) -> dict[str, str]:
    return {"kind": kind.value, "id": str(entity_id)}


@dataclass(frozen=True, slots=True)
class WorkAbsorptionRecord:
    id: UUID
    business_id: UUID
    outcome_run_id: UUID
    work_item_id: UUID | None
    task_type: TaskType
    previous_execution_mode: ExecutionMode
    current_execution_mode: ExecutionMode
    human_steps_before: int
    human_steps_after: int
    estimated_minutes_saved: int
    business_intervention_seconds: int | None
    internal_intervention_seconds: int | None
    automation_level: AutomationLevel
    evidence_ids: list[dict[str, str]]
    baseline_version: str
    created_at: datetime
    updated_at: datetime


def baseline_payload(task_type: TaskType) -> dict[str, Any]:
    spec = BASELINE_V1[task_type]
    mode = spec.current_execution_mode
    return {
        "task_type": task_type.value,
        "previous_execution_mode": spec.previous_execution_mode.value,
        "current_execution_mode": mode.value,
        "human_steps_before": spec.human_steps_before,
        "human_steps_after": spec.human_steps_after,
        "estimated_minutes_saved": spec.estimated_minutes_saved,
        "automation_level": automation_level_for(mode).value,
        "baseline_version": BASELINE_VERSION,
        "business_intervention_seconds": None,
        "internal_intervention_seconds": None,
    }


def total_baseline_minutes_saved() -> int:
    return sum(spec.estimated_minutes_saved for spec in BASELINE_V1.values())
