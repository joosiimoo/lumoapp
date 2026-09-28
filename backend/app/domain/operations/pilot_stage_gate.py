from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from fractions import Fraction
from typing import Any, Mapping
from uuid import UUID

from app.domain.operations.pilot_perception import (
    CLASSIFICATION_VERSION,
    AntiPosClassification,
    classify_anti_pos,
    is_delegation_positive,
    is_proactive_information_positive,
    is_sufficient_capture,
)

POLICY_VERSION = "build_a_stage_gate@1"
BUILD_IDENTIFIER = "mvp_build_a"

MIN_ELIGIBLE_OUTCOMES_PER_BUSINESS = 5
MIN_QUALIFYING_BUSINESSES_PER_COHORT = 3
MIN_COMPLETION_RATE = Fraction(90, 100)
MIN_DELEGATION_PERCEPTION_RATE = Fraction(70, 100)
MIN_PROACTIVE_INFORMATION_RATE = Fraction(60, 100)


class OverallStatus(StrEnum):
    READY = "ready"
    NOT_READY = "not_ready"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CriterionStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceQuality(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    MERCHANT_REPORTED = "merchant_reported"
    DERIVED = "derived"
    UNAVAILABLE = "unavailable"


class ScopeType(StrEnum):
    BUSINESS = "business"
    COHORT = "cohort"


class OutcomeStatusAtCutoff(StrEnum):
    IN_PROGRESS = "in_progress"
    READY = "ready"
    COMPLETED = "completed"


BLOCKING_BUSINESS_CRITERIA = frozenset(
    {
        "sample_size_eligible_outcomes",
        "outcome_completion_rate",
        "work_absorption_steps_reduced",
        "source_coverage_limitation_on_record",
        "outcome_cost_rows_present",
        "delegation_perception",
        "proactive_information_delivery",
    }
)

BLOCKING_COHORT_EXTRA = frozenset({"cohort_merchant_count"})


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    kind: str
    id: UUID

    def to_json(self) -> dict[str, str]:
        return {"kind": self.kind, "id": str(self.id)}


@dataclass(frozen=True, slots=True)
class CriterionResult:
    criterion_code: str
    status: CriterionStatus
    evidence_quality: EvidenceQuality
    observed_value: dict[str, Any]
    threshold_rule: str
    reason_code: str
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    per_business: dict[str, dict[str, Any]] | None = None

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "criterion_code": self.criterion_code,
            "status": self.status.value,
            "evidence_quality": self.evidence_quality.value,
            "observed_value": self.observed_value,
            "threshold_rule": self.threshold_rule,
            "reason_code": self.reason_code,
            "evidence_refs": [ref.to_json() for ref in self.evidence_refs],
        }
        if self.per_business is not None:
            payload["per_business"] = self.per_business
        return payload


@dataclass(frozen=True, slots=True)
class OutcomeRunSnapshot:
    outcome_run_id: UUID
    operational_day_id: UUID
    business_date: date
    created_at: datetime
    ready_at: datetime | None
    completed_at: datetime | None
    human_steps_before: int
    human_steps_after: int
    estimated_minutes_saved: int
    confirmation_task_count: int
    has_outcome_cost: bool
    has_source_coverage_limitation: bool
    open_work_items_at_cutoff: int


EnrollmentRange = tuple[date, date | None]


@dataclass(frozen=True, slots=True)
class PerceptionCaptureEvidence:
    capture_id: UUID
    response_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class BusinessEvaluationSnapshot:
    business_id: UUID
    outcome_runs: tuple[OutcomeRunSnapshot, ...]
    perception_answers: Mapping[str, str] | None
    perception_evidence: PerceptionCaptureEvidence | None


@dataclass(frozen=True, slots=True)
class AssessmentResult:
    overall_status: OverallStatus
    criterion_results: tuple[CriterionResult, ...]
    included_outcome_run_refs: list[dict[str, str]]


def status_at_cutoff(
    *,
    created_at: datetime,
    ready_at: datetime | None,
    completed_at: datetime | None,
    evidence_cutoff_at: datetime,
) -> OutcomeStatusAtCutoff | None:
    if created_at > evidence_cutoff_at:
        return None
    if completed_at is not None and completed_at <= evidence_cutoff_at:
        return OutcomeStatusAtCutoff.COMPLETED
    if ready_at is not None and ready_at <= evidence_cutoff_at:
        return OutcomeStatusAtCutoff.READY
    return OutcomeStatusAtCutoff.IN_PROGRESS


def enrollment_active_on(
    *,
    business_date: date,
    pilot_started_on: date,
    pilot_ended_on: date | None,
) -> bool:
    if business_date < pilot_started_on:
        return False
    if pilot_ended_on is not None and business_date > pilot_ended_on:
        return False
    return True


def enrollment_active_for_ranges(
    business_date: date,
    pilot_enrollment_ranges: tuple[EnrollmentRange, ...],
) -> bool:
    return any(
        enrollment_active_on(
            business_date=business_date,
            pilot_started_on=started,
            pilot_ended_on=ended,
        )
        for started, ended in pilot_enrollment_ranges
    )


def perception_evidence_refs(evidence: PerceptionCaptureEvidence | None) -> list[EvidenceRef]:
    if evidence is None:
        return []
    refs = [EvidenceRef("pilot_perception_capture", evidence.capture_id)]
    refs.extend(EvidenceRef("pilot_perception_response", response_id) for response_id in evidence.response_ids)
    return refs


def _eligible_runs(
    snapshot: BusinessEvaluationSnapshot,
    *,
    window_start: date,
    window_end: date,
    evidence_cutoff_at: datetime,
    pilot_enrollment_ranges: tuple[EnrollmentRange, ...],
) -> list[tuple[OutcomeRunSnapshot, OutcomeStatusAtCutoff]]:
    eligible: list[tuple[OutcomeRunSnapshot, OutcomeStatusAtCutoff]] = []
    for run in snapshot.outcome_runs:
        if run.business_date < window_start or run.business_date > window_end:
            continue
        if not enrollment_active_for_ranges(run.business_date, pilot_enrollment_ranges):
            continue
        status = status_at_cutoff(
            created_at=run.created_at,
            ready_at=run.ready_at,
            completed_at=run.completed_at,
            evidence_cutoff_at=evidence_cutoff_at,
        )
        if status is None:
            continue
        eligible.append((run, status))
    return eligible


def _completion_counts(eligible: list[tuple[OutcomeRunSnapshot, OutcomeStatusAtCutoff]]) -> tuple[int, int]:
    total = len(eligible)
    completed = sum(1 for _, status in eligible if status == OutcomeStatusAtCutoff.COMPLETED)
    return completed, total


def _absorption_aggregate(
    eligible: list[tuple[OutcomeRunSnapshot, OutcomeStatusAtCutoff]],
) -> dict[str, int]:
    completed = [run for run, status in eligible if status == OutcomeStatusAtCutoff.COMPLETED]
    before = sum(run.human_steps_before for run in completed)
    after = sum(run.human_steps_after for run in completed)
    eliminated = before - after
    minutes = sum(run.estimated_minutes_saved for run in completed)
    return {
        "total_human_steps_before": before,
        "total_human_steps_after": after,
        "steps_eliminated": eliminated,
        "total_estimated_minutes_saved": minutes,
        "completed_run_count": len(completed),
    }


def _absorption_passes(metrics: dict[str, int]) -> bool:
    if metrics["completed_run_count"] == 0:
        return False
    return (
        metrics["total_human_steps_before"] > 0
        and metrics["total_human_steps_after"] < metrics["total_human_steps_before"]
        and metrics["steps_eliminated"] > 0
    )


def _rate_status(numerator: int, denominator: int, minimum: Fraction) -> CriterionStatus:
    if denominator == 0:
        return CriterionStatus.INSUFFICIENT_EVIDENCE
    rate = Fraction(numerator, denominator)
    if rate >= minimum:
        return CriterionStatus.PASS
    return CriterionStatus.FAIL


def _criterion(
    code: str,
    status: CriterionStatus,
    quality: EvidenceQuality,
    observed: dict[str, Any],
    threshold: str,
    reason: str,
    refs: list[EvidenceRef] | None = None,
    per_business: dict[str, dict[str, Any]] | None = None,
) -> CriterionResult:
    return CriterionResult(
        criterion_code=code,
        status=status,
        evidence_quality=quality,
        observed_value=observed,
        threshold_rule=threshold,
        reason_code=reason,
        evidence_refs=refs or [],
        per_business=per_business,
    )


def evaluate_business_scope(
    snapshot: BusinessEvaluationSnapshot,
    *,
    evidence_window_start: date,
    evidence_window_end: date,
    evidence_cutoff_at: datetime,
    pilot_enrollment_ranges: tuple[EnrollmentRange, ...],
) -> AssessmentResult:
    eligible = _eligible_runs(
        snapshot,
        window_start=evidence_window_start,
        window_end=evidence_window_end,
        evidence_cutoff_at=evidence_cutoff_at,
        pilot_enrollment_ranges=pilot_enrollment_ranges,
    )
    refs = [
        {"business_id": str(snapshot.business_id), "outcome_run_id": str(run.outcome_run_id)}
        for run, _ in eligible
    ]
    results: list[CriterionResult] = []

    eligible_count = len(eligible)
    if eligible_count >= MIN_ELIGIBLE_OUTCOMES_PER_BUSINESS:
        sample_status = CriterionStatus.PASS
        sample_reason = "min_eligible_outcomes_met"
    else:
        sample_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        sample_reason = "below_min_eligible_outcomes"
    results.append(
        _criterion(
            "sample_size_eligible_outcomes",
            sample_status,
            EvidenceQuality.MEASURED,
            {"eligible_count": eligible_count, "minimum": MIN_ELIGIBLE_OUTCOMES_PER_BUSINESS},
            f"{POLICY_VERSION}/min_eligible_outcomes_per_business",
            sample_reason,
        )
    )

    completed, total = _completion_counts(eligible)
    if sample_status == CriterionStatus.PASS:
        completion_status = _rate_status(completed, total, MIN_COMPLETION_RATE)
        completion_reason = "completion_rate_evaluated"
    else:
        completion_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        completion_reason = "sample_insufficient"
    results.append(
        _criterion(
            "outcome_completion_rate",
            completion_status,
            EvidenceQuality.DERIVED,
            {"completed": completed, "eligible": total, "rate": str(Fraction(completed, total) if total else "0")},
            f"{POLICY_VERSION}/min_completion_rate",
            completion_reason,
        )
    )

    absorption = _absorption_aggregate(eligible)
    if absorption["completed_run_count"] == 0:
        absorption_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        absorption_reason = "no_completed_eligible_runs"
    elif _absorption_passes(absorption):
        absorption_status = CriterionStatus.PASS
        absorption_reason = "steps_reduced"
    else:
        absorption_status = CriterionStatus.FAIL
        absorption_reason = "no_structural_reduction"
    ratio = (
        str(Fraction(absorption["steps_eliminated"], absorption["total_human_steps_before"]))
        if absorption["total_human_steps_before"] > 0
        else None
    )
    results.append(
        _criterion(
            "work_absorption_steps_reduced",
            absorption_status,
            EvidenceQuality.ESTIMATED,
            {**absorption, "absorbed_step_ratio": ratio},
            f"{POLICY_VERSION}/structural_absorption",
            absorption_reason,
        )
    )

    completed_runs = [run for run, status in eligible if status == OutcomeStatusAtCutoff.COMPLETED]
    missing_coverage = [
        run for run in completed_runs if not run.has_source_coverage_limitation
    ]
    missing_cost = [run for run in completed_runs if not run.has_outcome_cost]
    if not completed_runs:
        coverage_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        cost_status = CriterionStatus.INSUFFICIENT_EVIDENCE
    else:
        coverage_status = CriterionStatus.PASS if not missing_coverage else CriterionStatus.FAIL
        cost_status = CriterionStatus.PASS if not missing_cost else CriterionStatus.FAIL
    results.append(
        _criterion(
            "source_coverage_limitation_on_record",
            coverage_status,
            EvidenceQuality.MEASURED,
            {"missing_count": len(missing_coverage), "completed_count": len(completed_runs)},
            f"{POLICY_VERSION}/limitation_on_record",
            "evaluated",
            [EvidenceRef("outcome_run", run.outcome_run_id) for run in completed_runs],
        )
    )
    results.append(
        _criterion(
            "outcome_cost_rows_present",
            cost_status,
            EvidenceQuality.MEASURED,
            {"missing_count": len(missing_cost), "completed_count": len(completed_runs)},
            f"{POLICY_VERSION}/outcome_cost_row",
            "evaluated",
        )
    )

    answers = snapshot.perception_answers
    perception_refs = perception_evidence_refs(snapshot.perception_evidence)
    if answers is None or not is_sufficient_capture(answers):
        delegation_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        proactive_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        delegation_reason = proactive_reason = "no_sufficient_capture"
    else:
        delegation_status = (
            CriterionStatus.PASS if is_delegation_positive(answers) else CriterionStatus.FAIL
        )
        proactive_status = (
            CriterionStatus.PASS
            if is_proactive_information_positive(answers)
            else CriterionStatus.FAIL
        )
        delegation_reason = proactive_reason = "evaluated"
    results.append(
        _criterion(
            "delegation_perception",
            delegation_status,
            EvidenceQuality.MERCHANT_REPORTED,
            {"positive": delegation_status == CriterionStatus.PASS},
            f"{POLICY_VERSION}/delegation_business",
            delegation_reason,
            perception_refs if delegation_reason == "evaluated" else [],
        )
    )
    results.append(
        _criterion(
            "proactive_information_delivery",
            proactive_status,
            EvidenceQuality.MERCHANT_REPORTED,
            {"positive": proactive_status == CriterionStatus.PASS},
            f"{POLICY_VERSION}/proactive_business",
            proactive_reason,
            perception_refs if proactive_reason == "evaluated" else [],
        )
    )

    results.extend(_diagnostic_results(snapshot, eligible, answers, perception_refs))

    overall = compose_overall(results, scope=ScopeType.BUSINESS)
    return AssessmentResult(overall_status=overall, criterion_results=tuple(results), included_outcome_run_refs=refs)


def evaluate_cohort_scope(
    snapshots: list[BusinessEvaluationSnapshot],
    *,
    evidence_window_start: date,
    evidence_window_end: date,
    evidence_cutoff_at: datetime,
    enrollments: Mapping[UUID, tuple[EnrollmentRange, ...]],
) -> AssessmentResult:
    qualifying: list[BusinessEvaluationSnapshot] = []
    per_business_sub: dict[str, dict[str, Any]] = {}
    all_refs: list[dict[str, str]] = []

    for snapshot in snapshots:
        pilot_ranges = enrollments[snapshot.business_id]
        eligible = _eligible_runs(
            snapshot,
            window_start=evidence_window_start,
            window_end=evidence_window_end,
            evidence_cutoff_at=evidence_cutoff_at,
            pilot_enrollment_ranges=pilot_ranges,
        )
        for run, _ in eligible:
            all_refs.append(
                {"business_id": str(snapshot.business_id), "outcome_run_id": str(run.outcome_run_id)}
            )
        if len(eligible) >= MIN_ELIGIBLE_OUTCOMES_PER_BUSINESS:
            qualifying.append(snapshot)
            completed, total = _completion_counts(eligible)
            per_business_sub[str(snapshot.business_id)] = {
                "eligible_count": len(eligible),
                "completed_at_cutoff": completed,
                "completion_rate": str(Fraction(completed, total) if total else "0"),
                "absorption": _absorption_aggregate(eligible),
            }

    results: list[CriterionResult] = []
    qualifying_count = len(qualifying)
    if qualifying_count >= MIN_QUALIFYING_BUSINESSES_PER_COHORT:
        cohort_count_status = CriterionStatus.PASS
        cohort_count_reason = "min_qualifying_businesses_met"
    else:
        cohort_count_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        cohort_count_reason = "below_min_qualifying_businesses"
    results.append(
        _criterion(
            "cohort_merchant_count",
            cohort_count_status,
            EvidenceQuality.MEASURED,
            {"qualifying_businesses": qualifying_count, "minimum": MIN_QUALIFYING_BUSINESSES_PER_COHORT},
            f"{POLICY_VERSION}/min_qualifying_businesses",
            cohort_count_reason,
        )
    )

    if cohort_count_status != CriterionStatus.PASS:
        completion_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        pooled_completed = pooled_total = 0
    else:
        pooled_completed = 0
        pooled_total = 0
        for snapshot in qualifying:
            pilot_ranges = enrollments[snapshot.business_id]
            eligible = _eligible_runs(
                snapshot,
                window_start=evidence_window_start,
                window_end=evidence_window_end,
                evidence_cutoff_at=evidence_cutoff_at,
                pilot_enrollment_ranges=pilot_ranges,
            )
            c, t = _completion_counts(eligible)
            pooled_completed += c
            pooled_total += t
        completion_status = _rate_status(pooled_completed, pooled_total, MIN_COMPLETION_RATE)
    results.append(
        _criterion(
            "outcome_completion_rate",
            completion_status,
            EvidenceQuality.DERIVED,
            {
                "completed": pooled_completed,
                "eligible": pooled_total,
                "rate": str(Fraction(pooled_completed, pooled_total) if pooled_total else "0"),
            },
            f"{POLICY_VERSION}/pooled_completion_rate",
            "evaluated" if cohort_count_status == CriterionStatus.PASS else "cohort_sample_insufficient",
            per_business=per_business_sub,
        )
    )

    if cohort_count_status != CriterionStatus.PASS:
        absorption_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        absorption_reason = "cohort_sample_insufficient"
    else:
        absorption_status = CriterionStatus.PASS
        absorption_reason = "all_qualifying_businesses_pass"
        for snapshot in qualifying:
            pilot_ranges = enrollments[snapshot.business_id]
            eligible = _eligible_runs(
                snapshot,
                window_start=evidence_window_start,
                window_end=evidence_window_end,
                evidence_cutoff_at=evidence_cutoff_at,
                pilot_enrollment_ranges=pilot_ranges,
            )
            metrics = _absorption_aggregate(eligible)
            if not _absorption_passes(metrics):
                absorption_status = CriterionStatus.FAIL
                absorption_reason = f"business_{snapshot.business_id}_failed_absorption"
                break
    pooled_absorption = {"qualifying_businesses": qualifying_count}
    results.append(
        _criterion(
            "work_absorption_steps_reduced",
            absorption_status,
            EvidenceQuality.ESTIMATED,
            pooled_absorption,
            f"{POLICY_VERSION}/per_business_structural_absorption",
            absorption_reason,
            per_business={k: v.get("absorption", {}) for k, v in per_business_sub.items()},
        )
    )

    if cohort_count_status != CriterionStatus.PASS:
        coverage_status = cost_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        missing_coverage = missing_cost = 0
        completed_count = 0
    else:
        missing_coverage = missing_cost = 0
        completed_count = 0
        for snapshot in qualifying:
            pilot_ranges = enrollments[snapshot.business_id]
            eligible = _eligible_runs(
                snapshot,
                window_start=evidence_window_start,
                window_end=evidence_window_end,
                evidence_cutoff_at=evidence_cutoff_at,
                pilot_enrollment_ranges=pilot_ranges,
            )
            completed_runs = [run for run, st in eligible if st == OutcomeStatusAtCutoff.COMPLETED]
            completed_count += len(completed_runs)
            missing_coverage += sum(1 for run in completed_runs if not run.has_source_coverage_limitation)
            missing_cost += sum(1 for run in completed_runs if not run.has_outcome_cost)
        coverage_status = CriterionStatus.PASS if missing_coverage == 0 and completed_count else CriterionStatus.FAIL
        cost_status = CriterionStatus.PASS if missing_cost == 0 and completed_count else CriterionStatus.FAIL
        if completed_count == 0:
            coverage_status = cost_status = CriterionStatus.INSUFFICIENT_EVIDENCE
    results.append(
        _criterion(
            "source_coverage_limitation_on_record",
            coverage_status,
            EvidenceQuality.MEASURED,
            {"missing_count": missing_coverage, "completed_count": completed_count},
            f"{POLICY_VERSION}/limitation_on_record",
            "evaluated",
        )
    )
    results.append(
        _criterion(
            "outcome_cost_rows_present",
            cost_status,
            EvidenceQuality.MEASURED,
            {"missing_count": missing_cost, "completed_count": completed_count},
            f"{POLICY_VERSION}/outcome_cost_row",
            "evaluated",
        )
    )

    sufficient_businesses = [
        s
        for s in snapshots
        if s.perception_answers is not None and is_sufficient_capture(s.perception_answers)
    ]
    if len(sufficient_businesses) < MIN_QUALIFYING_BUSINESSES_PER_COHORT:
        delegation_status = proactive_status = CriterionStatus.INSUFFICIENT_EVIDENCE
        delegation_obs = proactive_obs = {"sufficient_businesses": len(sufficient_businesses)}
        delegation_reason = proactive_reason = "below_min_perception_businesses"
    else:
        delegation_positive = sum(
            1 for s in sufficient_businesses if is_delegation_positive(s.perception_answers or {})
        )
        proactive_positive = sum(
            1
            for s in sufficient_businesses
            if is_proactive_information_positive(s.perception_answers or {})
        )
        denom = len(sufficient_businesses)
        delegation_status = _rate_status(delegation_positive, denom, MIN_DELEGATION_PERCEPTION_RATE)
        proactive_status = _rate_status(proactive_positive, denom, MIN_PROACTIVE_INFORMATION_RATE)
        delegation_obs = {
            "positive_businesses": delegation_positive,
            "denominator_businesses": denom,
        }
        proactive_obs = {
            "positive_businesses": proactive_positive,
            "denominator_businesses": denom,
        }
        delegation_reason = proactive_reason = "evaluated"
    cohort_perception_refs: list[EvidenceRef] = []
    for snapshot in sufficient_businesses:
        cohort_perception_refs.extend(perception_evidence_refs(snapshot.perception_evidence))
    results.append(
        _criterion(
            "delegation_perception",
            delegation_status,
            EvidenceQuality.MERCHANT_REPORTED,
            delegation_obs,
            f"{POLICY_VERSION}/delegation_cohort_rate",
            delegation_reason,
            cohort_perception_refs if delegation_reason == "evaluated" else [],
        )
    )
    results.append(
        _criterion(
            "proactive_information_delivery",
            proactive_status,
            EvidenceQuality.MERCHANT_REPORTED,
            proactive_obs,
            f"{POLICY_VERSION}/proactive_cohort_rate",
            proactive_reason,
            cohort_perception_refs if proactive_reason == "evaluated" else [],
        )
    )

    for snapshot in snapshots:
        pilot_ranges = enrollments[snapshot.business_id]
        eligible = _eligible_runs(
            snapshot,
            window_start=evidence_window_start,
            window_end=evidence_window_end,
            evidence_cutoff_at=evidence_cutoff_at,
            pilot_enrollment_ranges=pilot_ranges,
        )
        results.extend(
            _diagnostic_results(
                snapshot,
                eligible,
                snapshot.perception_answers,
                perception_evidence_refs(snapshot.perception_evidence),
                prefix=f"{snapshot.business_id}:",
            )
        )

    overall = compose_overall(results, scope=ScopeType.COHORT)
    return AssessmentResult(
        overall_status=overall,
        criterion_results=tuple(results),
        included_outcome_run_refs=all_refs,
    )


def compose_overall(results: list[CriterionResult], *, scope: ScopeType) -> OverallStatus:
    blocking = set(BLOCKING_BUSINESS_CRITERIA)
    if scope == ScopeType.COHORT:
        blocking |= BLOCKING_COHORT_EXTRA
    for result in results:
        if result.criterion_code not in blocking:
            continue
        if result.status == CriterionStatus.FAIL:
            return OverallStatus.NOT_READY
    for result in results:
        if result.criterion_code not in blocking:
            continue
        if result.status == CriterionStatus.INSUFFICIENT_EVIDENCE:
            return OverallStatus.INSUFFICIENT_EVIDENCE
    return OverallStatus.READY


def _diagnostic_results(
    snapshot: BusinessEvaluationSnapshot,
    eligible: list[tuple[OutcomeRunSnapshot, OutcomeStatusAtCutoff]],
    answers: Mapping[str, str] | None,
    perception_refs: list[EvidenceRef],
    *,
    prefix: str = "",
) -> list[CriterionResult]:
    confirmation_tasks = sum(run.confirmation_task_count for run, _ in eligible)
    open_items = sum(run.open_work_items_at_cutoff for run, _ in eligible)
    classification = (
        classify_anti_pos(answers).value
        if answers and is_sufficient_capture(answers)
        else AntiPosClassification.INSUFFICIENT_EVIDENCE.value
    )
    code_prefix = prefix
    return [
        _criterion(
            f"{code_prefix}merchant_confirmation_exposure",
            CriterionStatus.INSUFFICIENT_EVIDENCE,
            EvidenceQuality.MEASURED,
            {"confirmation_task_count": confirmation_tasks},
            f"{POLICY_VERSION}/diagnostic",
            "non_blocking",
        ),
        _criterion(
            f"{code_prefix}internal_intervention_evidence",
            CriterionStatus.INSUFFICIENT_EVIDENCE,
            EvidenceQuality.UNAVAILABLE,
            {},
            f"{POLICY_VERSION}/diagnostic",
            "no_review_task_instrumentation",
        ),
        _criterion(
            f"{code_prefix}unresolved_work_items_at_cutoff",
            CriterionStatus.INSUFFICIENT_EVIDENCE,
            EvidenceQuality.MEASURED,
            {"open_count": open_items},
            f"{POLICY_VERSION}/diagnostic_open_threshold",
            "non_blocking",
        ),
        _criterion(
            f"{code_prefix}outcome_cost_complete",
            CriterionStatus.INSUFFICIENT_EVIDENCE,
            EvidenceQuality.UNAVAILABLE,
            {},
            f"{POLICY_VERSION}/diagnostic",
            "non_blocking",
        ),
        _criterion(
            f"{code_prefix}anti_pos_classification",
            CriterionStatus.INSUFFICIENT_EVIDENCE,
            EvidenceQuality.MERCHANT_REPORTED,
            {"classification": classification},
            CLASSIFICATION_VERSION,
            "diagnostic",
            perception_refs if classification != AntiPosClassification.INSUFFICIENT_EVIDENCE.value else [],
        ),
        _criterion(
            f"{code_prefix}repeatability_sample_size",
            CriterionStatus.INSUFFICIENT_EVIDENCE,
            EvidenceQuality.UNAVAILABLE,
            {"policy": "deferred@2"},
            "build_a_stage_gate@2",
            "non_blocking",
        ),
    ]
