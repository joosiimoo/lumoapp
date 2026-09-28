from __future__ import annotations

from datetime import date, datetime, timezone
from fractions import Fraction
from uuid import UUID

import pytest

from app.domain.operations.pilot_perception import (
    AntiPosClassification,
    classify_anti_pos,
    is_delegation_positive,
    is_proactive_information_positive,
    is_sufficient_capture,
    select_latest_sufficient_capture,
)
from app.domain.operations.pilot_stage_gate import (
    BLOCKING_BUSINESS_CRITERIA,
    MIN_ELIGIBLE_OUTCOMES_PER_BUSINESS,
    MIN_QUALIFYING_BUSINESSES_PER_COHORT,
    POLICY_VERSION,
    OutcomeRunSnapshot,
    OutcomeStatusAtCutoff,
    OverallStatus,
    ScopeType,
    BusinessEvaluationSnapshot,
    CriterionStatus,
    compose_overall,
    evaluate_business_scope,
    evaluate_cohort_scope,
    status_at_cutoff,
)

UTC = timezone.utc
BID = UUID("00000000-0000-4000-8000-000000000001")
ANSWERS = {
    "close_organizer": "lumo",
    "information_delivery": "lumo_brings",
    "product_category": "operator_help",
    "workflow_ownership": "yes",
}


def _run(
    *,
    day: date,
    created: datetime,
    ready: datetime | None = None,
    completed: datetime | None = None,
    before: int = 6,
    after: int = 2,
    has_cost: bool = True,
    has_coverage: bool = True,
) -> OutcomeRunSnapshot:
    return OutcomeRunSnapshot(
        outcome_run_id=UUID(int=day.toordinal()),
        operational_day_id=UUID(int=day.toordinal() + 1),
        business_date=day,
        created_at=created,
        ready_at=ready,
        completed_at=completed,
        human_steps_before=before,
        human_steps_after=after,
        estimated_minutes_saved=before - after,
        confirmation_task_count=2,
        has_outcome_cost=has_cost,
        has_source_coverage_limitation=has_coverage,
        open_work_items_at_cutoff=0,
    )


def _business_snapshot(runs: list[OutcomeRunSnapshot], answers: dict[str, str] | None = None):
    return BusinessEvaluationSnapshot(
        business_id=BID,
        outcome_runs=tuple(runs),
        perception_answers=answers,
        perception_evidence=None,
    )


def test_status_at_cutoff_historical() -> None:
    cutoff = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    created = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    ready = datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
    completed = datetime(2026, 9, 21, 1, 0, tzinfo=UTC)
    assert (
        status_at_cutoff(
            created_at=created,
            ready_at=ready,
            completed_at=completed,
            evidence_cutoff_at=cutoff,
        )
        == OutcomeStatusAtCutoff.READY
    )
    assert (
        status_at_cutoff(
            created_at=created,
            ready_at=datetime(2026, 9, 21, 2, 0, tzinfo=UTC),
            completed_at=None,
            evidence_cutoff_at=cutoff,
        )
        == OutcomeStatusAtCutoff.IN_PROGRESS
    )
    assert (
        status_at_cutoff(
            created_at=datetime(2026, 9, 21, 2, 0, tzinfo=UTC),
            ready_at=None,
            completed_at=None,
            evidence_cutoff_at=cutoff,
        )
        is None
    )


def test_business_sample_insufficient_not_fail() -> None:
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    runs = [
        _run(
            day=date(2026, 9, d),
            created=cutoff,
            completed=cutoff,
        )
        for d in range(1, 5)
    ]
    result = evaluate_business_scope(
        _business_snapshot(runs),
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        pilot_enrollment_ranges=((date(2026, 9, 1), None),),
    )
    sample = next(r for r in result.criterion_results if r.criterion_code == "sample_size_eligible_outcomes")
    assert sample.status == CriterionStatus.INSUFFICIENT_EVIDENCE
    assert result.overall_status == OverallStatus.INSUFFICIENT_EVIDENCE


def test_business_completion_pass_and_fail() -> None:
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    runs = []
    for d in range(1, 6):
        completed = cutoff if d <= 5 else None
        runs.append(_run(day=date(2026, 9, d), created=cutoff, completed=completed))
    result = evaluate_business_scope(
        _business_snapshot(runs),
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        pilot_enrollment_ranges=((date(2026, 9, 1), None),),
    )
    completion = next(r for r in result.criterion_results if r.criterion_code == "outcome_completion_rate")
    assert completion.status == CriterionStatus.PASS

    runs_fail = runs[:4] + [_run(day=date(2026, 9, 5), created=cutoff, ready=cutoff)]
    result_fail = evaluate_business_scope(
        _business_snapshot(runs_fail),
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        pilot_enrollment_ranges=((date(2026, 9, 1), None),),
    )
    completion_fail = next(
        r for r in result_fail.criterion_results if r.criterion_code == "outcome_completion_rate"
    )
    assert completion_fail.status == CriterionStatus.FAIL
    assert result_fail.overall_status == OverallStatus.NOT_READY


def test_cohort_merchant_count_insufficient_for_two() -> None:
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    snapshots = []
    enrollments = {}
    for index in range(2):
        bid = UUID(int=index + 2)
        enrollments[bid] = ((date(2026, 9, 1), None),)
        runs = [
            _run(day=date(2026, 9, d), created=cutoff, completed=cutoff)
            for d in range(1, 6)
        ]
        snapshots.append(
            BusinessEvaluationSnapshot(business_id=bid, outcome_runs=tuple(runs), perception_answers=None, perception_evidence=None)
        )
    result = evaluate_cohort_scope(
        snapshots,
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        enrollments=enrollments,
    )
    cohort_count = next(r for r in result.criterion_results if r.criterion_code == "cohort_merchant_count")
    assert cohort_count.status == CriterionStatus.INSUFFICIENT_EVIDENCE
    assert result.overall_status == OverallStatus.INSUFFICIENT_EVIDENCE


def test_cohort_pooled_completion_with_per_business_diagnostic() -> None:
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    snapshots = []
    enrollments = {}
    for index, completed_days in enumerate((10, 10, 8)):
        bid = UUID(int=index + 10)
        enrollments[bid] = ((date(2026, 9, 1), None),)
        runs = []
        for d in range(1, 11):
            if d <= completed_days:
                runs.append(_run(day=date(2026, 9, d), created=cutoff, completed=cutoff))
            else:
                runs.append(_run(day=date(2026, 9, d), created=cutoff, ready=cutoff))
        snapshots.append(
            BusinessEvaluationSnapshot(business_id=bid, outcome_runs=tuple(runs), perception_answers=None, perception_evidence=None)
        )
    result = evaluate_cohort_scope(
        snapshots,
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        enrollments=enrollments,
    )
    completion = next(r for r in result.criterion_results if r.criterion_code == "outcome_completion_rate")
    assert completion.status == CriterionStatus.PASS
    assert completion.observed_value["rate"] == str(Fraction(28, 30))
    assert completion.per_business is not None
    third_bid = UUID(int=12)
    assert completion.per_business[str(third_bid)]["completion_rate"] == str(Fraction(8, 10))


def test_delegation_and_proactive_thresholds() -> None:
    answers = {
        "close_organizer": "lumo",
        "information_delivery": "lumo_brings",
        "product_category": "operator_help",
        "workflow_ownership": "yes",
    }
    assert is_sufficient_capture(answers)
    assert is_delegation_positive(answers)
    assert is_proactive_information_positive(answers)
    assert classify_anti_pos(answers) == AntiPosClassification.OPERATOR_PERCEIVED


def test_policy_version_is_build_a_stage_gate_at_1() -> None:
    assert POLICY_VERSION == "build_a_stage_gate@1"


def test_historical_completed_after_cutoff_not_counted() -> None:
    cutoff = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    created = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)
    completed_after = datetime(2026, 9, 21, 1, 0, tzinfo=UTC)
    runs = [
        _run(day=date(2026, 9, d), created=created, completed=cutoff if d <= 4 else completed_after)
        for d in range(1, 6)
    ]
    result = evaluate_business_scope(
        _business_snapshot(runs),
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        pilot_enrollment_ranges=((date(2026, 9, 1), None),),
    )
    completion = next(r for r in result.criterion_results if r.criterion_code == "outcome_completion_rate")
    assert completion.observed_value["completed"] == 4
    assert completion.observed_value["eligible"] == 5
    assert completion.status == CriterionStatus.FAIL


def test_cohort_does_not_pool_days_across_merchants_for_sample() -> None:
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    snapshots = []
    enrollments = {}
    for index in range(5):
        bid = UUID(int=index + 100)
        enrollments[bid] = ((date(2026, 9, 1), None),)
        runs = [_run(day=date(2026, 9, 1), created=cutoff, completed=cutoff)]
        snapshots.append(
            BusinessEvaluationSnapshot(
                business_id=bid,
                outcome_runs=tuple(runs),
                perception_answers=None,
                perception_evidence=None,
            )
        )
    result = evaluate_cohort_scope(
        snapshots,
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        enrollments=enrollments,
    )
    cohort_count = next(r for r in result.criterion_results if r.criterion_code == "cohort_merchant_count")
    assert cohort_count.status == CriterionStatus.INSUFFICIENT_EVIDENCE
    assert cohort_count.observed_value["qualifying_businesses"] == 0


def test_cohort_pooled_completion_fails_below_threshold() -> None:
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    snapshots = []
    enrollments = {}
    for index, completed_days in enumerate((10, 10, 6)):
        bid = UUID(int=index + 20)
        enrollments[bid] = ((date(2026, 9, 1), None),)
        runs = []
        for d in range(1, 11):
            if d <= completed_days:
                runs.append(_run(day=date(2026, 9, d), created=cutoff, completed=cutoff))
            else:
                runs.append(_run(day=date(2026, 9, d), created=cutoff, ready=cutoff))
        snapshots.append(
            BusinessEvaluationSnapshot(business_id=bid, outcome_runs=tuple(runs), perception_answers=None, perception_evidence=None)
        )
    result = evaluate_cohort_scope(
        snapshots,
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        enrollments=enrollments,
    )
    completion = next(r for r in result.criterion_results if r.criterion_code == "outcome_completion_rate")
    assert completion.status == CriterionStatus.FAIL
    assert completion.observed_value["rate"] == str(Fraction(26, 30))


def test_anti_pos_classification_matrix() -> None:
    pos_like = {
        "close_organizer": "merchant",
        "information_delivery": "merchant_searches",
        "product_category": "operator_help",
        "workflow_ownership": "no",
    }
    assert classify_anti_pos(pos_like) == AntiPosClassification.POS_LIKE
    another_system = {**ANSWERS, "product_category": "another_system"}
    assert classify_anti_pos(another_system) == AntiPosClassification.POS_LIKE
    mixed = {
        "close_organizer": "lumo",
        "information_delivery": "mixed",
        "product_category": "mixed",
        "workflow_ownership": "yes",
    }
    assert classify_anti_pos(mixed) == AntiPosClassification.MIXED
    assert classify_anti_pos({"close_organizer": "unsure", "information_delivery": "unsure", "product_category": "unsure", "workflow_ownership": "unsure"}) == AntiPosClassification.INSUFFICIENT_EVIDENCE


def test_select_latest_sufficient_capture_respects_cutoff() -> None:
    early = datetime(2026, 9, 10, tzinfo=UTC)
    late = datetime(2026, 9, 25, tzinfo=UTC)
    captures = [
        (early, ANSWERS),
        (late, {**ANSWERS, "information_delivery": "merchant_searches"}),
    ]
    cutoff = datetime(2026, 9, 20, tzinfo=UTC)
    selected = select_latest_sufficient_capture(captures, evidence_cutoff_at=cutoff)
    assert selected == ANSWERS
    selected_late = select_latest_sufficient_capture(captures, evidence_cutoff_at=datetime(2026, 9, 30, tzinfo=UTC))
    assert selected_late is not None
    assert selected_late["information_delivery"] == "merchant_searches"


def test_compose_overall_respects_blocking_only() -> None:
    from app.domain.operations.pilot_stage_gate import CriterionResult, EvidenceQuality

    blocking_pass = [
        CriterionResult(
            criterion_code=code,
            status=CriterionStatus.PASS,
            evidence_quality=EvidenceQuality.MEASURED,
            observed_value={},
            threshold_rule="t",
            reason_code="r",
        )
        for code in BLOCKING_BUSINESS_CRITERIA
    ]
    diagnostic = CriterionResult(
        criterion_code="internal_intervention_evidence",
        status=CriterionStatus.INSUFFICIENT_EVIDENCE,
        evidence_quality=EvidenceQuality.UNAVAILABLE,
        observed_value={},
        threshold_rule="t",
        reason_code="r",
    )
    assert compose_overall([*blocking_pass, diagnostic], scope=ScopeType.BUSINESS) == OverallStatus.READY
