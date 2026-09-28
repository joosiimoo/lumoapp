from __future__ import annotations

import pytest
from app.domain.shared.ids import new_uuid7
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.domain.operations.outcome_cost import ComponentStatus, CostCompleteness
from app.domain.operations.work_absorption import (
    BASELINE_VERSION,
    ALL_TASK_TYPES,
    ExecutionMode,
    TaskType,
    automation_level_for,
    baseline_payload,
    total_baseline_minutes_saved,
)
from app.infrastructure.persistence.models import (
    OutcomeCostRow,
    OutcomeRunRow,
    WorkAbsorptionRecordRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from tests.sale_cleanup import sale_integrity_orphans
from tests.test_business_stream import _get
from tests.test_daily_close_confirmation import _confirm, _ready, _seed
from tests.test_daily_close_preparation import _cash_sale
from tests.test_work_items import _audits


def _close_day(client: TestClient, token: str, prefix: str) -> None:
    confirmation, _ = _ready(client, token, prefix)
    response = _confirm(client, token, prefix, confirmation)
    assert response.status_code == 200, response.text


def test_execution_mode_and_automation_rollup() -> None:
    assert automation_level_for(ExecutionMode.MANUAL_BY_BUSINESS).value == "manual"
    assert automation_level_for(ExecutionMode.ASSISTED_BY_LUMO).value == "assisted"
    assert automation_level_for(ExecutionMode.PREPARED_BY_LUMO).value == "assisted"
    assert automation_level_for(ExecutionMode.EXECUTED_WITH_CONFIRMATION).value == "assisted"
    assert automation_level_for(ExecutionMode.FULLY_AUTOMATED).value == "automated"
    assert automation_level_for(ExecutionMode.EXECUTED_UNDER_POLICY).value == "automated"
    with pytest.raises(ValueError):
        ExecutionMode("not_a_mode")


def test_baseline_v1_values() -> None:
    assert total_baseline_minutes_saved() == 8
    organize = baseline_payload(TaskType.ORGANIZE_REGISTERED_SALES)
    assert organize["baseline_version"] == BASELINE_VERSION
    assert organize["human_steps_before"] == 1 and organize["human_steps_after"] == 0
    assert organize["estimated_minutes_saved"] == 2
    assert organize["current_execution_mode"] == ExecutionMode.FULLY_AUTOMATED.value
    assert organize["previous_execution_mode"] == ExecutionMode.MANUAL_BY_BUSINESS.value
    record = baseline_payload(TaskType.RECORD_CASH_COUNT)
    assert record["estimated_minutes_saved"] == 0
    assert record["current_execution_mode"] == ExecutionMode.EXECUTED_WITH_CONFIRMATION.value
    assert record["business_intervention_seconds"] is None
    assert record["internal_intervention_seconds"] is None


def test_daily_close_writes_six_absorption_rows_and_cost(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    prefix = "abs-close"
    _close_day(client, token, prefix)
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    run = db_session.scalar(
        select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id)
    )
    assert run is not None and run.status == "completed"
    rows = db_session.scalars(
        select(WorkAbsorptionRecordRow).where(
            WorkAbsorptionRecordRow.business_id == tenant.business_id,
            WorkAbsorptionRecordRow.outcome_run_id == run.id,
        )
    ).all()
    assert len(rows) == 6
    modes = {row.current_execution_mode for row in rows}
    assert modes == {
        ExecutionMode.FULLY_AUTOMATED.value,
        ExecutionMode.PREPARED_BY_LUMO.value,
        ExecutionMode.EXECUTED_WITH_CONFIRMATION.value,
    }
    assert sum(row.estimated_minutes_saved for row in rows) == 8
    assert all(row.business_intervention_seconds is None for row in rows)
    assert all(row.internal_intervention_seconds is None for row in rows)
    assert all(row.baseline_version == BASELINE_VERSION for row in rows)
    cost = db_session.scalar(
        select(OutcomeCostRow).where(
            OutcomeCostRow.business_id == tenant.business_id,
            OutcomeCostRow.outcome_run_id == run.id,
        )
    )
    assert cost is not None
    assert cost.currency == "USD"
    assert cost.model_call_count is None and cost.model_call_count_status == ComponentStatus.UNAVAILABLE.value
    assert cost.model_cost_amount is None and cost.model_cost_status == ComponentStatus.UNAVAILABLE.value
    assert cost.infrastructure_cost_amount is None
    assert cost.retry_count == 0 and cost.retry_count_status == ComponentStatus.MEASURED.value
    assert cost.estimated_total_cost_amount is None
    assert cost.cost_completeness == CostCompleteness.PARTIAL.value
    assert cost.business_intervention_seconds is None
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_idempotent_commit_and_recount_do_not_duplicate(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    prefix = "abs-idem"
    _cash_sale(client, token, prefix, "900gr zanahoria")
    _cash_sale(client, token, f"{prefix}-2", "900gr zanahoria")
    from tests.test_daily_close_confirmation import _post

    set_current_business_id(db_session, tenant.business_id)
    _post(client, token, "conté 22.50", f"{prefix}-count", f"conv-{prefix}")
    _post(client, token, "conté 22.50", f"{prefix}-recount", f"conv-{prefix}")
    count_absorption = db_session.scalar(
        select(func.count())
        .select_from(WorkAbsorptionRecordRow)
        .where(WorkAbsorptionRecordRow.business_id == tenant.business_id)
    )
    assert count_absorption == 4
    cost_count = db_session.scalar(
        select(func.count()).select_from(OutcomeCostRow).where(OutcomeCostRow.business_id == tenant.business_id)
    )
    assert cost_count == 1


def test_completed_outcome_rejects_instrumentation_mutations(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _close_day(client, token, "abs-freeze")
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    run = db_session.scalar(select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id))
    assert run is not None
    set_current_business_id(db_session, tenant.business_id)
    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                """
                INSERT INTO operations.work_absorption_records (
                    id, business_id, outcome_run_id, work_item_id, task_type,
                    previous_execution_mode, current_execution_mode,
                    human_steps_before, human_steps_after, estimated_minutes_saved,
                    business_intervention_seconds, internal_intervention_seconds,
                    automation_level, evidence_ids, baseline_version, created_at, updated_at
                ) VALUES (
                    :new_id, :business_id, :outcome_run_id, NULL, 'prepare_close',
                    'manual_by_business', 'prepared_by_lumo', 1, 0, 2,
                    NULL, NULL, 'assisted', '[]'::jsonb,
                    'daily_close_ready@1/work_absorption_baseline@1', now(), now()
                )
                """
            ),
            {"new_id": new_uuid7(), "business_id": tenant.business_id, "outcome_run_id": run.id},
        )
        db_session.commit()
    db_session.rollback()
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    row = db_session.scalar(
        select(WorkAbsorptionRecordRow).where(
            WorkAbsorptionRecordRow.business_id == tenant.business_id,
            WorkAbsorptionRecordRow.task_type == TaskType.ORGANIZE_REGISTERED_SALES.value,
        )
    )
    assert row is not None
    with pytest.raises(DBAPIError):
        db_session.execute(
            text(
                """
                UPDATE operations.work_absorption_records
                SET estimated_minutes_saved = 99
                WHERE id = :id AND business_id = :business_id
                """
            ),
            {"id": row.id, "business_id": tenant.business_id},
        )
        db_session.commit()
    db_session.rollback()
    set_current_business_id(db_session, tenant.business_id)


def test_business_stream_get_does_not_write_absorption(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    prefix = "abs-stream"
    _ready(client, token, prefix)
    before = db_session.scalar(
        select(func.count()).select_from(WorkAbsorptionRecordRow).where(
            WorkAbsorptionRecordRow.business_id == tenant.business_id
        )
    )
    assert _get(client, token).status_code == 200
    assert _get(client, token).status_code == 200
    after = db_session.scalar(
        select(func.count()).select_from(WorkAbsorptionRecordRow).where(
            WorkAbsorptionRecordRow.business_id == tenant.business_id
        )
    )
    assert before == after


def test_audit_created_once_per_insert(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _close_day(client, token, "abs-audit")
    assert len(_audits(db_session, tenant.business_id, "work_absorption.created")) == 6
    assert len(_audits(db_session, tenant.business_id, "outcome_cost.created")) == 1


def test_intervention_semantics_build_a_null_baseline_and_persistence(db_session, client: TestClient) -> None:
    """Task 7.4: NULL in Build A, measured zero allowed, NULL != 0, negatives rejected, no minute derivation."""
    for task_type in ALL_TASK_TYPES:
        payload = baseline_payload(task_type)
        assert payload["business_intervention_seconds"] is None
        assert payload["internal_intervention_seconds"] is None
        if payload["estimated_minutes_saved"] > 0:
            assert payload["business_intervention_seconds"] != payload["estimated_minutes_saved"] * 60

    tenant, token = _seed(db_session)
    _cash_sale(client, token, "int-sem", "900gr zanahoria")
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    run = db_session.scalar(
        select(OutcomeRunRow).where(
            OutcomeRunRow.business_id == tenant.business_id,
            OutcomeRunRow.status == "in_progress",
        )
    )
    assert run is not None
    cost = db_session.scalar(
        select(OutcomeCostRow).where(
            OutcomeCostRow.business_id == tenant.business_id,
            OutcomeCostRow.outcome_run_id == run.id,
        )
    )
    assert cost is not None
    assert cost.business_intervention_seconds is None
    assert cost.internal_intervention_seconds is None

    null_row = db_session.scalar(
        select(WorkAbsorptionRecordRow).where(
            WorkAbsorptionRecordRow.business_id == tenant.business_id,
            WorkAbsorptionRecordRow.task_type == TaskType.ORGANIZE_REGISTERED_SALES.value,
        )
    )
    zero_row = db_session.scalar(
        select(WorkAbsorptionRecordRow).where(
            WorkAbsorptionRecordRow.business_id == tenant.business_id,
            WorkAbsorptionRecordRow.task_type == TaskType.CALCULATE_EXPECTED_CASH.value,
        )
    )
    assert null_row is not None and zero_row is not None
    assert null_row.business_intervention_seconds is None
    assert null_row.internal_intervention_seconds is None

    zero_row.business_intervention_seconds = 0
    zero_row.internal_intervention_seconds = 0
    cost.business_intervention_seconds = 0
    cost.internal_intervention_seconds = 0
    db_session.commit()
    db_session.expire_all()
    set_current_business_id(db_session, tenant.business_id)

    reread_null = db_session.get(WorkAbsorptionRecordRow, null_row.id)
    reread_zero = db_session.get(WorkAbsorptionRecordRow, zero_row.id)
    reread_cost = db_session.get(OutcomeCostRow, cost.id)
    assert reread_null is not None and reread_zero is not None and reread_cost is not None
    assert reread_null.business_intervention_seconds is None
    assert reread_null.internal_intervention_seconds is None
    assert reread_zero.business_intervention_seconds == 0
    assert reread_zero.internal_intervention_seconds == 0
    assert reread_cost.business_intervention_seconds == 0
    assert reread_cost.internal_intervention_seconds == 0
    assert reread_null.business_intervention_seconds is not reread_zero.business_intervention_seconds

    with pytest.raises(DBAPIError):
        zero_row.business_intervention_seconds = -1
        db_session.commit()
    db_session.rollback()
    set_current_business_id(db_session, tenant.business_id)

    tenant_close, token_close = _seed(db_session)
    _close_day(client, token_close, "int-sem-close")
    set_current_business_id(db_session, tenant_close.business_id)
    db_session.expire_all()
    closed_run = db_session.scalar(
        select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant_close.business_id)
    )
    assert closed_run is not None and closed_run.status == "completed"
    closed_rows = db_session.scalars(
        select(WorkAbsorptionRecordRow).where(WorkAbsorptionRecordRow.outcome_run_id == closed_run.id)
    ).all()
    closed_cost = db_session.scalar(
        select(OutcomeCostRow).where(OutcomeCostRow.outcome_run_id == closed_run.id)
    )
    assert closed_cost is not None
    assert len(closed_rows) == 6
    assert all(row.business_intervention_seconds is None for row in closed_rows)
    assert all(row.internal_intervention_seconds is None for row in closed_rows)
    assert closed_cost.business_intervention_seconds is None
    assert closed_cost.internal_intervention_seconds is None


def test_rls_hides_instrumentation_from_other_tenant(client: TestClient, db_session) -> None:
    tenant_a, token_a = _seed(db_session)
    _close_day(client, token_a, "abs-rls-a")
    set_current_business_id(db_session, tenant_a.business_id)
    absorption_a = db_session.scalars(select(WorkAbsorptionRecordRow)).all()
    cost_a = db_session.scalars(select(OutcomeCostRow)).all()
    assert len(absorption_a) == 6
    assert len(cost_a) == 1
    absorption_ids_a = {row.id for row in absorption_a}
    cost_ids_a = {row.id for row in cost_a}

    tenant_b, _token_b = _seed(db_session)
    set_current_business_id(db_session, tenant_b.business_id)
    db_session.expire_all()
    visible_absorption = db_session.scalars(select(WorkAbsorptionRecordRow)).all()
    visible_cost = db_session.scalars(select(OutcomeCostRow)).all()
    assert not any(row.id in absorption_ids_a for row in visible_absorption)
    assert not any(row.id in cost_ids_a for row in visible_cost)
    assert all(row.business_id == tenant_b.business_id for row in visible_absorption)
    assert all(row.business_id == tenant_b.business_id for row in visible_cost)
