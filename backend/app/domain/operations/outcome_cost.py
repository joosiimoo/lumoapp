from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

PLATFORM_COST_CURRENCY = "USD"


class ComponentStatus(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


class CostCompleteness(StrEnum):
    PARTIAL = "partial"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class OutcomeCost:
    id: UUID
    business_id: UUID
    outcome_run_id: UUID
    currency: str
    model_call_count: int | None
    model_call_count_status: ComponentStatus
    prompt_tokens: int | None
    completion_tokens: int | None
    model_token_status: ComponentStatus
    model_cost_amount: Decimal | None
    model_cost_status: ComponentStatus
    infrastructure_cost_amount: Decimal | None
    infrastructure_cost_status: ComponentStatus
    retry_count: int
    retry_count_status: ComponentStatus
    business_intervention_seconds: int | None
    internal_intervention_seconds: int | None
    estimated_total_cost_amount: Decimal | None
    cost_completeness: CostCompleteness
    created_at: datetime
    updated_at: datetime


def new_build_a_outcome_cost(
    *,
    id: UUID,
    business_id: UUID,
    outcome_run_id: UUID,
    created_at: datetime,
    updated_at: datetime,
    retry_count: int = 0,
) -> OutcomeCost:
    """Build A Daily Close: unavailable model/infra money, partial total, NULL intervention."""
    return OutcomeCost(
        id=id,
        business_id=business_id,
        outcome_run_id=outcome_run_id,
        currency=PLATFORM_COST_CURRENCY,
        model_call_count=None,
        model_call_count_status=ComponentStatus.UNAVAILABLE,
        prompt_tokens=None,
        completion_tokens=None,
        model_token_status=ComponentStatus.UNAVAILABLE,
        model_cost_amount=None,
        model_cost_status=ComponentStatus.UNAVAILABLE,
        infrastructure_cost_amount=None,
        infrastructure_cost_status=ComponentStatus.UNAVAILABLE,
        retry_count=retry_count,
        retry_count_status=ComponentStatus.MEASURED,
        business_intervention_seconds=None,
        internal_intervention_seconds=None,
        estimated_total_cost_amount=None,
        cost_completeness=CostCompleteness.PARTIAL,
        created_at=created_at,
        updated_at=updated_at,
    )
