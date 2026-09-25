from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.operations.cash_count import CashStatus
from app.domain.operations.day import OperationalDayStatus

SOURCE_DAILY_CLOSE_RULE = "daily_close_rule"
RESPONSIBLE_PARTY_BUSINESS = "business"


class WorkItemType(StrEnum):
    CASH_COUNT_REQUIRED = "cash_count_required"
    CASH_DIFFERENCE_REVIEW = "cash_difference_review"
    CLOSE_CONFIRMATION_REQUIRED = "close_confirmation_required"


class WorkItemStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class WorkItemPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"


class ResolutionActorType(StrEnum):
    BUSINESS = "business"
    SYSTEM = "system"


class ResolutionCode(StrEnum):
    CASH_COUNT_RECORDED = "cash_count_recorded"
    CASH_BALANCED = "cash_balanced"
    DAY_CLOSED = "day_closed"
    CASH_UNBALANCED = "cash_unbalanced"


class ReasonCode(StrEnum):
    CASH_COUNT_MISSING = "cash_count_missing"
    CASH_SHORT = "cash_short"
    CASH_OVER = "cash_over"
    CLOSE_CONFIRMATION_REQUIRED = "close_confirmation_required"


RANKED_TYPES = (
    WorkItemType.CASH_COUNT_REQUIRED,
    WorkItemType.CASH_DIFFERENCE_REVIEW,
    WorkItemType.CLOSE_CONFIRMATION_REQUIRED,
)


@dataclass(frozen=True, slots=True)
class WorkItem:
    id: UUID
    business_id: UUID
    operational_day_id: UUID
    type: WorkItemType
    status: WorkItemStatus
    priority: WorkItemPriority
    responsible_party: str
    reason_code: str
    source: str
    evidence: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    resolution_actor_type: ResolutionActorType | None = None
    resolved_by_actor_id: UUID | None = None
    resolution_code: ResolutionCode | None = None
    outcome_run_id: UUID | None = None


def priority_for(item_type: WorkItemType) -> WorkItemPriority:
    if item_type is WorkItemType.CASH_COUNT_REQUIRED:
        return WorkItemPriority.CRITICAL
    if item_type is WorkItemType.CASH_DIFFERENCE_REVIEW:
        return WorkItemPriority.HIGH
    return WorkItemPriority.NORMAL


def reason_code_for(item_type: WorkItemType, cash_status: CashStatus | None) -> ReasonCode:
    if item_type is WorkItemType.CASH_COUNT_REQUIRED:
        return ReasonCode.CASH_COUNT_MISSING
    if item_type is WorkItemType.CASH_DIFFERENCE_REVIEW:
        if cash_status is CashStatus.OVER:
            return ReasonCode.CASH_OVER
        return ReasonCode.CASH_SHORT
    return ReasonCode.CLOSE_CONFIRMATION_REQUIRED


def desired_open_type(
    *,
    day_status: OperationalDayStatus | None,
    sale_count: int,
    cash_status: CashStatus | None,
) -> WorkItemType | None:
    """At most one open Daily Close type. Short or over is only the difference row."""
    if day_status is None or day_status is OperationalDayStatus.CLOSED or sale_count < 1:
        return None
    if cash_status is None or cash_status is CashStatus.NOT_COUNTED:
        return WorkItemType.CASH_COUNT_REQUIRED
    if cash_status in {CashStatus.SHORT, CashStatus.OVER}:
        return WorkItemType.CASH_DIFFERENCE_REVIEW
    if cash_status is CashStatus.BALANCED:
        return WorkItemType.CLOSE_CONFIRMATION_REQUIRED
    return None


def resolution_for(
    *,
    open_type: WorkItemType,
    desired_type: WorkItemType | None,
    closing: bool,
) -> tuple[ResolutionCode, ResolutionActorType] | None:
    """How an open row leaves the desired set. None means keep it."""
    if closing:
        return (ResolutionCode.DAY_CLOSED, ResolutionActorType.BUSINESS)
    if desired_type is None or open_type is desired_type:
        return None
    if open_type is WorkItemType.CASH_COUNT_REQUIRED:
        return (ResolutionCode.CASH_COUNT_RECORDED, ResolutionActorType.BUSINESS)
    if (
        open_type is WorkItemType.CASH_DIFFERENCE_REVIEW
        and desired_type is WorkItemType.CLOSE_CONFIRMATION_REQUIRED
    ):
        return (ResolutionCode.CASH_BALANCED, ResolutionActorType.SYSTEM)
    if (
        open_type is WorkItemType.CLOSE_CONFIRMATION_REQUIRED
        and desired_type is WorkItemType.CASH_DIFFERENCE_REVIEW
    ):
        return (ResolutionCode.CASH_UNBALANCED, ResolutionActorType.SYSTEM)
    return None
