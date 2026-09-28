from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.domain.operations.pilot_stage_gate import ScopeType, evaluate_business_scope, evaluate_cohort_scope
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.engine import create_session_factory
from app.infrastructure.persistence.pilot_stage_gate import PilotStageGateRepository


def _as_sqlalchemy_url(value: str) -> str:
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _list_cohort_enrollments(
    admin_url: str,
    cohort_code: str,
    *,
    window_start: date,
    window_end: date,
) -> dict[UUID, tuple[tuple[date, date | None], ...]]:
    engine = create_engine(_as_sqlalchemy_url(admin_url), pool_pre_ping=True, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE operations.pilot_program_enrollments DISABLE ROW LEVEL SECURITY")
            )
            rows = connection.execute(
                text(
                    """
                    SELECT business_id, pilot_started_on, pilot_ended_on
                    FROM operations.pilot_program_enrollments
                    WHERE cohort_code = :cohort_code
                      AND daterange(
                            pilot_started_on,
                            COALESCE(pilot_ended_on, 'infinity'::date),
                            '[]'
                          ) && daterange(:window_start, :window_end, '[]')
                    """
                ),
                {
                    "cohort_code": cohort_code,
                    "window_start": window_start,
                    "window_end": window_end,
                },
            ).all()
            connection.execute(
                text("ALTER TABLE operations.pilot_program_enrollments ENABLE ROW LEVEL SECURITY")
            )
            connection.execute(
                text("ALTER TABLE operations.pilot_program_enrollments FORCE ROW LEVEL SECURITY")
            )
        grouped: dict[UUID, list[tuple[date, date | None]]] = {}
        for row in rows:
            grouped.setdefault(row.business_id, []).append((row.pilot_started_on, row.pilot_ended_on))
        return {business_id: tuple(ranges) for business_id, ranges in grouped.items()}
    finally:
        engine.dispose()


def assess_business_stage_gate(
    *,
    session: Session,
    tenant: TenantContext,
    cohort_code: str,
    evidence_window_start: date,
    evidence_window_end: date,
    evidence_cutoff_at: datetime,
    evaluated_at: datetime,
) -> UUID:
    repo = PilotStageGateRepository(session)
    enrollment_ranges = repo.list_enrollment_ranges_for_window(
        tenant=tenant,
        cohort_code=cohort_code,
        window_start=evidence_window_start,
        window_end=evidence_window_end,
    )
    if not enrollment_ranges:
        raise ValidationAppError("business is not enrolled in cohort for evidence window")
    existing = repo.find_existing_assessment(
        scope_type=ScopeType.BUSINESS.value,
        business_id=tenant.business_id,
        cohort_code=cohort_code,
        policy_version="build_a_stage_gate@1",
        evidence_window_start=evidence_window_start,
        evidence_window_end=evidence_window_end,
        evidence_cutoff_at=evidence_cutoff_at,
    )
    if existing is not None:
        return existing.id
    snapshot = repo.load_business_snapshot(
        business_id=tenant.business_id,
        evidence_cutoff_at=evidence_cutoff_at,
    )
    result = evaluate_business_scope(
        snapshot,
        evidence_window_start=evidence_window_start,
        evidence_window_end=evidence_window_end,
        evidence_cutoff_at=evidence_cutoff_at,
        pilot_enrollment_ranges=enrollment_ranges,
    )
    row = repo.persist_assessment(
        scope_type=ScopeType.BUSINESS,
        business_id=tenant.business_id,
        cohort_code=cohort_code,
        evidence_window_start=evidence_window_start,
        evidence_window_end=evidence_window_end,
        evidence_cutoff_at=evidence_cutoff_at,
        evaluated_at=evaluated_at,
        result=result,
    )
    return row.id


def assess_cohort_stage_gate(
    *,
    admin_url: str,
    cohort_code: str,
    evidence_window_start: date,
    evidence_window_end: date,
    evidence_cutoff_at: datetime,
    evaluated_at: datetime,
) -> UUID:
    enrollments = _list_cohort_enrollments(
        admin_url,
        cohort_code,
        window_start=evidence_window_start,
        window_end=evidence_window_end,
    )
    if not enrollments:
        raise ValidationAppError("no enrollments for cohort")
    engine = create_engine(_as_sqlalchemy_url(admin_url), pool_pre_ping=True, future=True)
    factory = create_session_factory(engine)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE operations.stage_gate_assessments DISABLE ROW LEVEL SECURITY")
            )
            existing_id = connection.execute(
                text(
                    """
                    SELECT id FROM operations.stage_gate_assessments
                    WHERE scope_type = 'cohort'
                      AND business_id IS NULL
                      AND cohort_code = :cohort_code
                      AND policy_version = :policy_version
                      AND evidence_window_start = :window_start
                      AND evidence_window_end = :window_end
                      AND evidence_cutoff_at = :cutoff
                    """
                ),
                {
                    "cohort_code": cohort_code,
                    "policy_version": "build_a_stage_gate@1",
                    "window_start": evidence_window_start,
                    "window_end": evidence_window_end,
                    "cutoff": evidence_cutoff_at,
                },
            ).scalar_one_or_none()
            connection.execute(
                text("ALTER TABLE operations.stage_gate_assessments ENABLE ROW LEVEL SECURITY")
            )
            connection.execute(
                text("ALTER TABLE operations.stage_gate_assessments FORCE ROW LEVEL SECURITY")
            )
        if existing_id is not None:
            return existing_id

        snapshots = []
        for business_id in enrollments:
            session = factory()
            try:
                repo = PilotStageGateRepository(session)
                snapshots.append(
                    repo.load_business_snapshot(
                        business_id=business_id,
                        evidence_cutoff_at=evidence_cutoff_at,
                    )
                )
            finally:
                session.close()
        result = evaluate_cohort_scope(
            snapshots,
            evidence_window_start=evidence_window_start,
            evidence_window_end=evidence_window_end,
            evidence_cutoff_at=evidence_cutoff_at,
            enrollments=enrollments,
        )
        persist_session = factory()
        try:
            with persist_session.begin():
                connection = persist_session.connection()
                connection.execute(
                    text("ALTER TABLE operations.stage_gate_assessments DISABLE ROW LEVEL SECURITY")
                )
                repo = PilotStageGateRepository(persist_session)
                row = repo.persist_assessment(
                    scope_type=ScopeType.COHORT,
                    business_id=None,
                    cohort_code=cohort_code,
                    evidence_window_start=evidence_window_start,
                    evidence_window_end=evidence_window_end,
                    evidence_cutoff_at=evidence_cutoff_at,
                    evaluated_at=evaluated_at,
                    result=result,
                    included_business_ids=list(enrollments.keys()),
                )
                connection.execute(
                    text("ALTER TABLE operations.stage_gate_assessments ENABLE ROW LEVEL SECURITY")
                )
                connection.execute(
                    text("ALTER TABLE operations.stage_gate_assessments FORCE ROW LEVEL SECURITY")
                )
            return row.id
        finally:
            persist_session.close()
    finally:
        engine.dispose()
