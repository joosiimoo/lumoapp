from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import (
    OperationalDayRow,
    OutcomeRunRow,
    PilotPerceptionResponseRow,
    PilotProgramEnrollmentRow,
    StageGateAssessmentRow,
)
from app.infrastructure.persistence.pilot_stage_gate import PilotStageGateRepository
from app.infrastructure.persistence.pilot_stage_gate_runner import (
    assess_business_stage_gate,
    assess_cohort_stage_gate,
)
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, postgres_available, seed_business
from tests.test_daily_close_confirmation import _confirm, _ready, _seed
pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")

UTC = timezone.utc
COHORT = "build-a-pilot-integration"
ANSWERS = {
    "close_organizer": "lumo",
    "information_delivery": "lumo_brings",
    "product_category": "operator_help",
    "workflow_ownership": "yes",
}


def _close_day(client: TestClient, token: str, prefix: str) -> None:
    confirmation, _ = _ready(client, token, prefix)
    response = _confirm(client, token, prefix, confirmation)
    assert response.status_code == 200, response.text


def _record_perception(
    session,
    *,
    business_id,
    actor_id,
    capture_id,
    captured_at: datetime,
) -> None:
    tenant = TenantContext(business_id=business_id, actor_id=actor_id)
    PilotStageGateRepository(session).record_perception_capture(
        tenant=tenant,
        capture_id=capture_id,
        cohort_code=COHORT,
        answers=ANSWERS,
        captured_at=captured_at,
        capture_source="internal_interview",
    )


def test_perception_rls_isolated(db_session) -> None:
    business_a, user_a, _ = seed_business(db_session, name="Pilot Perception A")
    business_b, user_b, _ = seed_business(db_session, name="Pilot Perception B")
    captured_at = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    _record_perception(
        db_session,
        business_id=business_a,
        actor_id=user_a,
        capture_id=new_uuid7(),
        captured_at=captured_at,
    )
    db_session.commit()

    set_current_business_id(db_session, business_a)
    db_session.expire_all()
    visible_a = db_session.scalars(select(PilotPerceptionResponseRow)).all()
    assert len(visible_a) == 4

    set_current_business_id(db_session, business_b)
    db_session.expire_all()
    visible_b = db_session.scalars(select(PilotPerceptionResponseRow)).all()
    assert visible_b == []


def test_perception_append_only(db_session) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Append")
    _record_perception(
        db_session,
        business_id=business_id,
        actor_id=user_id,
        capture_id=new_uuid7(),
        captured_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    db_session.commit()
    set_current_business_id(db_session, business_id)
    row = db_session.scalars(select(PilotPerceptionResponseRow)).first()
    assert row is not None
    with pytest.raises(DBAPIError, match="append-only"):
        db_session.delete(row)
        db_session.commit()
    db_session.rollback()
    set_current_business_id(db_session, business_id)
    row = db_session.scalars(select(PilotPerceptionResponseRow)).first()
    assert row is not None
    with pytest.raises(DBAPIError, match="append-only"):
        row.response_code = "merchant"
        db_session.commit()


def test_finalized_assessment_immutable(db_session) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Immutable")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    repo = PilotStageGateRepository(db_session)
    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 9, 1),
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    cutoff = datetime(2026, 9, 30, 18, 0, tzinfo=UTC)
    assess_business_stage_gate(
        session=db_session,
        tenant=tenant,
        cohort_code=COHORT,
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        evaluated_at=cutoff,
    )
    db_session.commit()
    set_current_business_id(db_session, business_id)
    row = db_session.scalar(select(StageGateAssessmentRow))
    assert row is not None and row.finalized_at is not None
    with pytest.raises(DBAPIError, match="immutable"):
        row.overall_status = "ready"
        db_session.commit()
    db_session.rollback()
    set_current_business_id(db_session, business_id)
    row = db_session.scalar(select(StageGateAssessmentRow))
    assert row is not None
    with pytest.raises(DBAPIError, match="immutable"):
        db_session.delete(row)
        db_session.commit()


def test_merchant_cannot_read_cohort_assessments(db_session, settings) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Cohort RLS")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    repo = PilotStageGateRepository(db_session)
    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 9, 1),
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    assess_cohort_stage_gate(
        admin_url=settings.sqlalchemy_admin_url,
        cohort_code=COHORT,
        evidence_window_start=date(2026, 9, 1),
        evidence_window_end=date(2026, 9, 30),
        evidence_cutoff_at=cutoff,
        evaluated_at=cutoff,
    )
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    visible = db_session.scalars(select(StageGateAssessmentRow)).all()
    assert visible == []


def test_business_assessment_idempotency(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _close_day(client, token, "sg-idem")
    set_current_business_id(db_session, tenant.business_id)
    day = db_session.scalar(
        select(OperationalDayRow).where(OperationalDayRow.business_id == tenant.business_id)
    )
    assert day is not None
    business_ctx = TenantContext(business_id=tenant.business_id, actor_id=tenant.actor_id)
    PilotStageGateRepository(db_session).enroll_business(
        tenant=business_ctx,
        cohort_code=COHORT,
        pilot_started_on=day.business_date,
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    cutoff = datetime(2026, 9, 30, 23, 59, tzinfo=UTC)
    window_start = day.business_date
    window_end = day.business_date
    first_id = assess_business_stage_gate(
        session=db_session,
        tenant=business_ctx,
        cohort_code=COHORT,
        evidence_window_start=window_start,
        evidence_window_end=window_end,
        evidence_cutoff_at=cutoff,
        evaluated_at=cutoff,
    )
    db_session.commit()
    second_id = assess_business_stage_gate(
        session=db_session,
        tenant=business_ctx,
        cohort_code=COHORT,
        evidence_window_start=window_start,
        evidence_window_end=window_end,
        evidence_cutoff_at=cutoff,
        evaluated_at=cutoff,
    )
    db_session.commit()
    assert first_id == second_id
    set_current_business_id(db_session, tenant.business_id)
    count = db_session.scalar(
        select(func.count()).select_from(StageGateAssessmentRow).where(
            StageGateAssessmentRow.business_id == tenant.business_id
        )
    )
    assert count == 1

    later_cutoff = datetime(2026, 10, 1, tzinfo=UTC)
    third_id = assess_business_stage_gate(
        session=db_session,
        tenant=business_ctx,
        cohort_code=COHORT,
        evidence_window_start=window_start,
        evidence_window_end=window_end,
        evidence_cutoff_at=later_cutoff,
        evaluated_at=later_cutoff,
    )
    db_session.commit()
    assert third_id != first_id
    set_current_business_id(db_session, tenant.business_id)
    count = db_session.scalar(
        select(func.count()).select_from(StageGateAssessmentRow).where(
            StageGateAssessmentRow.business_id == tenant.business_id
        )
    )
    assert count == 2


def test_assess_is_read_only_on_outcome_runs(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _close_day(client, token, "sg-readonly")
    set_current_business_id(db_session, tenant.business_id)
    before = db_session.scalar(
        select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id)
    )
    assert before is not None
    snapshot = {
        "status": before.status,
        "ready_at": before.ready_at,
        "completed_at": before.completed_at,
        "reason_code": before.reason_code,
        "closing_snapshot_id": before.closing_snapshot_id,
    }
    day = db_session.scalar(
        select(OperationalDayRow).where(OperationalDayRow.business_id == tenant.business_id)
    )
    assert day is not None
    business_ctx = TenantContext(business_id=tenant.business_id, actor_id=tenant.actor_id)
    PilotStageGateRepository(db_session).enroll_business(
        tenant=business_ctx,
        cohort_code=COHORT,
        pilot_started_on=day.business_date,
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    assess_business_stage_gate(
        session=db_session,
        tenant=business_ctx,
        cohort_code=COHORT,
        evidence_window_start=day.business_date,
        evidence_window_end=day.business_date,
        evidence_cutoff_at=cutoff,
        evaluated_at=cutoff,
    )
    db_session.commit()
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    after = db_session.scalar(
        select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id)
    )
    assert after is not None
    assert after.status == snapshot["status"]
    assert after.ready_at == snapshot["ready_at"]
    assert after.completed_at == snapshot["completed_at"]
    assert after.reason_code == snapshot["reason_code"]
    assert after.closing_snapshot_id == snapshot["closing_snapshot_id"]


def test_overlapping_enrollment_rejected(db_session) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Enroll Overlap")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    repo = PilotStageGateRepository(db_session)
    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 9, 1),
        pilot_ended_on=date(2026, 9, 30),
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    from sqlalchemy.exc import DBAPIError

    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 9, 15),
        pilot_ended_on=date(2026, 10, 15),
        created_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    with pytest.raises(DBAPIError):
        db_session.commit()
    db_session.rollback()
    set_current_business_id(db_session, business_id)


def test_non_overlapping_reenrollment_allowed(db_session) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Reenroll")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    repo = PilotStageGateRepository(db_session)
    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 9, 1),
        pilot_ended_on=date(2026, 9, 30),
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 11, 1),
        pilot_ended_on=None,
        created_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    db_session.commit()
    set_current_business_id(db_session, business_id)
    rows = db_session.scalars(
        select(PilotProgramEnrollmentRow).where(PilotProgramEnrollmentRow.business_id == business_id)
    ).all()
    assert len(rows) == 2


def test_different_cohort_enrollment_allowed(db_session) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Two Cohorts")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    repo = PilotStageGateRepository(db_session)
    repo.enroll_business(
        tenant=tenant,
        cohort_code=COHORT,
        pilot_started_on=date(2026, 9, 1),
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    repo.enroll_business(
        tenant=tenant,
        cohort_code="build-a-pilot-alt",
        pilot_started_on=date(2026, 9, 1),
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    set_current_business_id(db_session, business_id)
    assert len(db_session.scalars(select(PilotProgramEnrollmentRow)).all()) == 2


def test_assessment_perception_evidence_refs(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _close_day(client, token, "sg-perception-refs")
    set_current_business_id(db_session, tenant.business_id)
    day = db_session.scalar(
        select(OperationalDayRow).where(OperationalDayRow.business_id == tenant.business_id)
    )
    assert day is not None
    capture_id = new_uuid7()
    _record_perception(
        db_session,
        business_id=tenant.business_id,
        actor_id=tenant.actor_id,
        capture_id=capture_id,
        captured_at=datetime(2026, 9, 15, tzinfo=UTC),
    )
    business_ctx = TenantContext(business_id=tenant.business_id, actor_id=tenant.actor_id)
    PilotStageGateRepository(db_session).enroll_business(
        tenant=business_ctx,
        cohort_code=COHORT,
        pilot_started_on=day.business_date,
        pilot_ended_on=None,
        created_at=datetime(2026, 9, 1, tzinfo=UTC),
    )
    db_session.commit()
    cutoff = datetime(2026, 9, 30, tzinfo=UTC)
    assessment_id = assess_business_stage_gate(
        session=db_session,
        tenant=business_ctx,
        cohort_code=COHORT,
        evidence_window_start=day.business_date,
        evidence_window_end=day.business_date,
        evidence_cutoff_at=cutoff,
        evaluated_at=cutoff,
    )
    db_session.commit()
    set_current_business_id(db_session, tenant.business_id)
    assessment = db_session.get(StageGateAssessmentRow, assessment_id)
    assert assessment is not None
    response_ids = {
        str(row.id)
        for row in db_session.scalars(
            select(PilotPerceptionResponseRow).where(
                PilotPerceptionResponseRow.capture_id == capture_id
            )
        ).all()
    }
    for code in ("delegation_perception", "proactive_information_delivery"):
        criterion = next(item for item in assessment.criterion_results if item["criterion_code"] == code)
        ref_ids = {ref["id"] for ref in criterion["evidence_refs"] if ref["kind"] == "pilot_perception_response"}
        assert ref_ids == response_ids
        assert any(ref["id"] == str(capture_id) and ref["kind"] == "pilot_perception_capture" for ref in criterion["evidence_refs"])
    anti_pos = next(
        item for item in assessment.criterion_results if item["criterion_code"] == "anti_pos_classification"
    )
    assert anti_pos["evidence_refs"]


def test_sufficient_perception_selected_at_cutoff(db_session) -> None:
    business_id, user_id, _ = seed_business(db_session, name="Pilot Capture Cutoff")
    tenant = TenantContext(business_id=business_id, actor_id=user_id)
    early_capture = new_uuid7()
    late_capture = new_uuid7()
    cutoff = datetime(2026, 9, 20, 12, 0, tzinfo=UTC)
    repo = PilotStageGateRepository(db_session)
    repo.record_perception_capture(
        tenant=tenant,
        capture_id=early_capture,
        cohort_code=COHORT,
        answers=ANSWERS,
        captured_at=datetime(2026, 9, 10, tzinfo=UTC),
        capture_source="internal_interview",
    )
    later_answers = {**ANSWERS, "information_delivery": "merchant_searches"}
    repo.record_perception_capture(
        tenant=tenant,
        capture_id=late_capture,
        cohort_code=COHORT,
        answers=later_answers,
        captured_at=datetime(2026, 9, 25, tzinfo=UTC),
        capture_source="internal_interview",
    )
    db_session.commit()
    repo = PilotStageGateRepository(db_session)
    snapshot = repo.load_business_snapshot(business_id=business_id, evidence_cutoff_at=cutoff)
    assert snapshot.perception_answers == ANSWERS

    snapshot_after_late = repo.load_business_snapshot(
        business_id=business_id,
        evidence_cutoff_at=datetime(2026, 9, 30, tzinfo=UTC),
    )
    assert snapshot_after_late.perception_answers == later_answers
