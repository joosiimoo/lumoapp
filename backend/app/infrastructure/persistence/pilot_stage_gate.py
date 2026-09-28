from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.operations.pilot_perception import (
    QUESTION_SET_VERSION,
    validate_capture_source,
    validate_question_code,
    validate_response_code,
)
from app.domain.operations.pilot_stage_gate import (
    BUILD_IDENTIFIER,
    POLICY_VERSION,
    AssessmentResult,
    BusinessEvaluationSnapshot,
    EnrollmentRange,
    OutcomeRunSnapshot,
    PerceptionCaptureEvidence,
    ScopeType,
    evaluate_business_scope,
    evaluate_cohort_scope,
)
from app.infrastructure.persistence.pilot_enrollment import enrollment_range_overlaps_window
from app.domain.operations.work_absorption import ExecutionMode
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import (
    OperationalDayRow,
    OutcomeCostRow,
    OutcomeRunRow,
    PilotPerceptionResponseRow,
    PilotProgramEnrollmentRow,
    SourceCoverageRecordRow,
    StageGateAssessmentRow,
    WorkAbsorptionRecordRow,
    WorkItemRow,
)
from app.infrastructure.persistence.rls import set_current_business_id


class PilotStageGateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enroll_business(
        self,
        *,
        tenant: TenantContext,
        cohort_code: str,
        pilot_started_on: date,
        pilot_ended_on: date | None,
        created_at: datetime,
    ) -> PilotProgramEnrollmentRow:
        set_current_business_id(self._session, tenant.business_id)
        row = PilotProgramEnrollmentRow(
            id=new_uuid7(),
            business_id=tenant.business_id,
            cohort_code=cohort_code,
            pilot_started_on=pilot_started_on,
            pilot_ended_on=pilot_ended_on,
            created_at=created_at,
        )
        self._session.add(row)
        return row

    def record_perception_capture(
        self,
        *,
        tenant: TenantContext,
        capture_id: UUID,
        cohort_code: str | None,
        answers: dict[str, str],
        captured_at: datetime,
        capture_source: str,
        note: str | None = None,
    ) -> None:
        validate_capture_source(capture_source)
        if note is not None and len(note) > 500:
            raise ValidationAppError("note exceeds 500 characters")
        set_current_business_id(self._session, tenant.business_id)
        for question_code, response_code in answers.items():
            validate_question_code(question_code)
            validate_response_code(question_code, response_code)
            self._session.add(
                PilotPerceptionResponseRow(
                    id=new_uuid7(),
                    business_id=tenant.business_id,
                    capture_id=capture_id,
                    cohort_code=cohort_code,
                    question_set_version=QUESTION_SET_VERSION,
                    question_code=question_code,
                    response_code=response_code,
                    note=note,
                    captured_at=captured_at,
                    capture_source=capture_source,
                )
            )

    def list_enrollment_ranges_for_window(
        self,
        *,
        tenant: TenantContext,
        cohort_code: str,
        window_start: date,
        window_end: date,
    ) -> tuple[EnrollmentRange, ...]:
        set_current_business_id(self._session, tenant.business_id)
        rows = self._session.scalars(
            select(PilotProgramEnrollmentRow).where(
                PilotProgramEnrollmentRow.business_id == tenant.business_id,
                PilotProgramEnrollmentRow.cohort_code == cohort_code,
            )
        ).all()
        matching = [
            (row.pilot_started_on, row.pilot_ended_on)
            for row in rows
            if enrollment_range_overlaps_window(
                pilot_started_on=row.pilot_started_on,
                pilot_ended_on=row.pilot_ended_on,
                window_start=window_start,
                window_end=window_end,
            )
        ]
        return tuple(matching)

    def list_cohort_business_ids(self, *, cohort_code: str) -> list[UUID]:
        rows = self._session.scalars(
            select(PilotProgramEnrollmentRow.business_id).where(
                PilotProgramEnrollmentRow.cohort_code == cohort_code
            )
        ).all()
        return list(rows)

    def load_business_snapshot(
        self,
        *,
        business_id: UUID,
        evidence_cutoff_at: datetime,
    ) -> BusinessEvaluationSnapshot:
        set_current_business_id(self._session, business_id)
        runs = self._session.execute(
            select(OutcomeRunRow, OperationalDayRow.business_date)
            .join(
                OperationalDayRow,
                (OutcomeRunRow.operational_day_id == OperationalDayRow.id)
                & (OutcomeRunRow.business_id == OperationalDayRow.business_id),
            )
            .where(OutcomeRunRow.business_id == business_id)
        ).all()
        snapshots: list[OutcomeRunSnapshot] = []
        for run, business_date in runs:
            absorption_rows = self._session.scalars(
                select(WorkAbsorptionRecordRow).where(
                    WorkAbsorptionRecordRow.outcome_run_id == run.id,
                    WorkAbsorptionRecordRow.business_id == business_id,
                )
            ).all()
            before = sum(row.human_steps_before for row in absorption_rows)
            after = sum(row.human_steps_after for row in absorption_rows)
            minutes = sum(row.estimated_minutes_saved for row in absorption_rows)
            confirmations = sum(
                1
                for row in absorption_rows
                if row.current_execution_mode == ExecutionMode.EXECUTED_WITH_CONFIRMATION.value
            )
            has_cost = (
                self._session.scalar(
                    select(OutcomeCostRow.id).where(
                        OutcomeCostRow.outcome_run_id == run.id,
                        OutcomeCostRow.business_id == business_id,
                    )
                )
                is not None
            )
            coverage = self._session.scalar(
                select(SourceCoverageRecordRow.id).where(
                    SourceCoverageRecordRow.business_id == business_id,
                    SourceCoverageRecordRow.operational_day_id == run.operational_day_id,
                    SourceCoverageRecordRow.limitation_code == "only_lumo_registered_operations",
                )
            )
            open_items = self._session.scalar(
                select(WorkItemRow.id)
                .where(
                    WorkItemRow.business_id == business_id,
                    WorkItemRow.operational_day_id == run.operational_day_id,
                    WorkItemRow.status == "open",
                    WorkItemRow.created_at <= evidence_cutoff_at,
                )
                .limit(1)
            )
            open_count = 1 if open_items is not None else 0
            unresolved = self._session.scalars(
                select(WorkItemRow).where(
                    WorkItemRow.business_id == business_id,
                    WorkItemRow.operational_day_id == run.operational_day_id,
                )
            ).all()
            open_at_cutoff = sum(
                1
                for item in unresolved
                if item.status == "open"
                or (item.resolved_at is not None and item.resolved_at > evidence_cutoff_at)
            )
            snapshots.append(
                OutcomeRunSnapshot(
                    outcome_run_id=run.id,
                    operational_day_id=run.operational_day_id,
                    business_date=business_date,
                    created_at=run.created_at,
                    ready_at=run.ready_at,
                    completed_at=run.completed_at,
                    human_steps_before=before,
                    human_steps_after=after,
                    estimated_minutes_saved=minutes,
                    confirmation_task_count=confirmations,
                    has_outcome_cost=has_cost,
                    has_source_coverage_limitation=coverage is not None,
                    open_work_items_at_cutoff=open_at_cutoff,
                )
            )
        perception_answers, perception_evidence = self._load_perception_capture(
            business_id, evidence_cutoff_at
        )
        return BusinessEvaluationSnapshot(
            business_id=business_id,
            outcome_runs=tuple(snapshots),
            perception_answers=perception_answers,
            perception_evidence=perception_evidence,
        )

    def _load_perception_capture(
        self, business_id: UUID, evidence_cutoff_at: datetime
    ) -> tuple[dict[str, str] | None, PerceptionCaptureEvidence | None]:
        rows = self._session.scalars(
            select(PilotPerceptionResponseRow)
            .where(
                PilotPerceptionResponseRow.business_id == business_id,
                PilotPerceptionResponseRow.captured_at <= evidence_cutoff_at,
            )
            .order_by(PilotPerceptionResponseRow.captured_at.desc())
        ).all()
        if not rows:
            return None, None
        by_capture: dict[UUID, dict[str, str]] = {}
        capture_times: dict[UUID, datetime] = {}
        rows_by_capture: dict[UUID, list[PilotPerceptionResponseRow]] = {}
        for row in rows:
            by_capture.setdefault(row.capture_id, {})[row.question_code] = row.response_code
            capture_times[row.capture_id] = row.captured_at
            rows_by_capture.setdefault(row.capture_id, []).append(row)
        ordered = sorted(capture_times.items(), key=lambda item: item[1], reverse=True)
        for capture_id, _ in ordered:
            answers = by_capture[capture_id]
            if len(answers) == 4 and all(v != "unsure" for v in answers.values()):
                response_ids = tuple(row.id for row in rows_by_capture[capture_id])
                return answers, PerceptionCaptureEvidence(capture_id=capture_id, response_ids=response_ids)
        return None, None

    def find_existing_assessment(
        self,
        *,
        scope_type: str,
        business_id: UUID | None,
        cohort_code: str,
        policy_version: str,
        evidence_window_start: date,
        evidence_window_end: date,
        evidence_cutoff_at: datetime,
    ) -> StageGateAssessmentRow | None:
        if business_id is not None:
            set_current_business_id(self._session, business_id)
        return self._session.scalar(
            select(StageGateAssessmentRow).where(
                StageGateAssessmentRow.scope_type == scope_type,
                StageGateAssessmentRow.business_id == business_id,
                StageGateAssessmentRow.cohort_code == cohort_code,
                StageGateAssessmentRow.policy_version == policy_version,
                StageGateAssessmentRow.evidence_window_start == evidence_window_start,
                StageGateAssessmentRow.evidence_window_end == evidence_window_end,
                StageGateAssessmentRow.evidence_cutoff_at == evidence_cutoff_at,
            )
        )

    def persist_assessment(
        self,
        *,
        scope_type: ScopeType,
        business_id: UUID | None,
        cohort_code: str,
        evidence_window_start: date,
        evidence_window_end: date,
        evidence_cutoff_at: datetime,
        evaluated_at: datetime,
        result: AssessmentResult,
        included_business_ids: list[UUID] | None = None,
    ) -> StageGateAssessmentRow:
        if business_id is not None:
            set_current_business_id(self._session, business_id)
        row = StageGateAssessmentRow(
            id=new_uuid7(),
            scope_type=scope_type.value,
            business_id=business_id,
            cohort_code=cohort_code,
            build_identifier=BUILD_IDENTIFIER,
            policy_version=POLICY_VERSION,
            evidence_window_start=evidence_window_start,
            evidence_window_end=evidence_window_end,
            evidence_cutoff_at=evidence_cutoff_at,
            overall_status=result.overall_status.value,
            criterion_results=[item.to_json() for item in result.criterion_results],
            included_outcome_run_refs=result.included_outcome_run_refs,
            included_business_ids=[str(bid) for bid in included_business_ids]
            if included_business_ids
            else None,
            evaluated_at=evaluated_at,
            finalized_at=evaluated_at,
        )
        self._session.add(row)
        return row
