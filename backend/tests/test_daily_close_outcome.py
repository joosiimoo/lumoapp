from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app.agent.registrations import register_conversational_sale_tools
from app.agent.tools import ToolRegistry
from app.application.workflows.initialize_open_work_items import initialize_open_today_work_items
from app.application.workflows.outcomes import EmptyOutcomeEngine, OutcomeStatus
from app.domain.operations import (
    OUTCOME_DEFINITION_ID,
    CashStatus,
    OperationalDayStatus,
    daily_close_ready_definition,
    derive_daily_close_outcome,
)
from app.domain.operations.daily_close_outcome import OutcomeReasonCode, OutcomeRunStatus
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.models import (
    AuditEventRow,
    OperationalDayRow,
    OutcomeRunRow,
    OutboxEventRow,
    WorkItemRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, seed_business
from tests.test_daily_close_confirmation import _confirm, _day, _post, _ready, _seed, _snapshots
from tests.test_daily_close_preparation import _cash_sale
from tests.test_work_items import _all_items, _audits, _count, _nba, _open_items


def test_predicate_maps_open_and_closed_facts_without_work_items() -> None:
    missing = derive_daily_close_outcome(
        day_status=OperationalDayStatus.OPEN,
        sale_count=1,
        cash_status=CashStatus.NOT_COUNTED,
        has_snapshot=False,
    )
    assert missing is not None
    assert missing.status is OutcomeRunStatus.IN_PROGRESS
    assert missing.reason_code is OutcomeReasonCode.AWAITING_CASH_COUNT
    balanced = derive_daily_close_outcome(
        day_status=OperationalDayStatus.OPEN,
        sale_count=2,
        cash_status=CashStatus.BALANCED,
        has_snapshot=False,
    )
    short = derive_daily_close_outcome(
        day_status=OperationalDayStatus.OPEN,
        sale_count=2,
        cash_status=CashStatus.SHORT,
        has_snapshot=False,
    )
    over = derive_daily_close_outcome(
        day_status=OperationalDayStatus.OPEN,
        sale_count=2,
        cash_status=CashStatus.OVER,
        has_snapshot=False,
    )
    assert balanced is not None and balanced.reason_code is OutcomeReasonCode.READY_BALANCED
    assert short is not None and short.reason_code is OutcomeReasonCode.READY_CASH_SHORT
    assert over is not None and over.reason_code is OutcomeReasonCode.READY_CASH_OVER
    closed = derive_daily_close_outcome(
        day_status=OperationalDayStatus.CLOSED,
        sale_count=2,
        cash_status=CashStatus.SHORT,
        has_snapshot=True,
    )
    assert closed is not None
    assert closed.status is OutcomeRunStatus.COMPLETED
    assert closed.reason_code is OutcomeReasonCode.CLOSED_CONFIRMED
    assert (
        derive_daily_close_outcome(
            day_status=None,
            sale_count=0,
            cash_status=None,
            has_snapshot=False,
        )
        is None
    )


def test_registered_engine_evaluates_only_daily_close_ready(client: TestClient, db_session) -> None:
    engine = client.app.state.outcome_engine
    assert engine.registered_ids() == (OUTCOME_DEFINITION_ID,)
    definition = daily_close_ready_definition()
    assert definition["version"] == 1
    assert definition["owner_type"] == "business"
    assert definition["trigger"] == "first_confirmed_sale"
    assert definition["output_artifact"] == "ClosingSnapshot"
    assert definition["states"] == ["in_progress", "ready", "completed"]
    status = engine.evaluate(
        OUTCOME_DEFINITION_ID,
        {
            "day_status": "open",
            "sale_count": 1,
            "cash_status": "not_counted",
            "has_snapshot": False,
        },
        model_claim="completed",
    )
    assert status == "in_progress"
    assert engine.evaluate("daily_sales_operations_ready@1", {"sale_count": 1}, model_claim="ready") == (
        OutcomeStatus.NOT_READY
    )
    bare = EmptyOutcomeEngine()
    assert bare.evaluate(OUTCOME_DEFINITION_ID, {"sale_count": 1}) == OutcomeStatus.NOT_READY
    with pytest.raises(ValidationAppError):
        engine.evaluate(OUTCOME_DEFINITION_ID, {"day_status": "open", "sale_count": 0}, model_claim="ready")
    tools = ToolRegistry()
    register_conversational_sale_tools(tools)
    assert tools.is_registered("daily_close_ready.execute@1") is False
    tenant, token = _seed(db_session)
    before = _outcomes(db_session, tenant.business_id)
    engine.evaluate("daily_sales_operations_ready@1", {"sale_count": 3}, model_claim="completed")
    assert _outcomes(db_session, tenant.business_id) == before
    assert token


def test_first_and_second_sale_share_one_in_progress_run(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-first", "900gr zanahoria")
    runs = _outcomes(db_session, tenant.business_id)
    assert len(runs) == 1
    first = runs[0]
    assert first.status == "in_progress"
    assert first.reason_code == "awaiting_cash_count"
    assert first.ready_at is None
    assert first.completed_at is None
    assert first.closing_snapshot_id is None
    assert first.owner_type == "business"
    assert first.outcome_type == "daily_close_ready"
    assert first.outcome_version == 1
    assert first.evidence["cash_status"] == "not_counted"
    assert "current_cash_count_id" not in first.evidence
    assert "operational_day_id" not in first.evidence
    assert isinstance(first.evidence["expected_cash"], str)
    assert isinstance(first.evidence["gross_sales_total"], str)
    item = _open_items(db_session, tenant.business_id)[0]
    assert item.type == "cash_count_required"
    assert item.outcome_run_id == first.id
    created = _audits(db_session, tenant.business_id, "outcome_run.created")
    assert len(created) == 1
    assert created[0].route_or_tool == "sale.commit@1"
    assert created[0].after_payload["status"] == "in_progress"
    _cash_sale(client, token, "out-second", "500gr tomate")
    again = _outcomes(db_session, tenant.business_id)
    assert len(again) == 1
    assert again[0].id == first.id
    assert again[0].status == "in_progress"
    assert again[0].ready_at is None
    assert again[0].evidence["sale_count"] == 2
    assert len(_audits(db_session, tenant.business_id, "outcome_run.created")) == 1
    assert _audits(db_session, tenant.business_id, "outcome_run.status_changed") == []
    assert _count(db_session, tenant.business_id, OutboxEventRow, event_type="outcome_run.created") == 0


def test_ready_reasons_keep_difference_work_open(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-bal", "900gr zanahoria")
    _forget_outcome(db_session, tenant.business_id)
    counted = _post(client, token, "conté 22.50", "out-bal-count", "conv-out-bal")
    assert counted.status_code == 200, counted.text
    balanced = _outcomes(db_session, tenant.business_id)[0]
    assert balanced.status == "ready"
    assert balanced.reason_code == "ready_balanced"
    assert balanced.ready_at is not None
    assert balanced.ready_at == balanced.created_at
    assert _audits(db_session, tenant.business_id, "outcome_run.status_changed") == []
    created = _audits(db_session, tenant.business_id, "outcome_run.created")
    assert any(
        row.after_payload["outcome_run_id"] == str(balanced.id) and row.after_payload["status"] == "ready"
        for row in created
    )

    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-short", "900gr zanahoria")
    short_count = _post(client, token, "conté 20.00", "out-short-count", "conv-out-short")
    assert short_count.status_code == 200, short_count.text
    short = _outcomes(db_session, tenant.business_id)[0]
    assert short.status == "ready"
    assert short.reason_code == "ready_cash_short"
    assert short.ready_at is not None
    assert _open_items(db_session, tenant.business_id)[0].type == "cash_difference_review"
    assert _open_items(db_session, tenant.business_id)[0].outcome_run_id == short.id

    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-over", "900gr zanahoria")
    over_count = _post(client, token, "conté 30.00", "out-over-count", "conv-out-over")
    assert over_count.status_code == 200, over_count.text
    over = _outcomes(db_session, tenant.business_id)[0]
    assert over.reason_code == "ready_cash_over"
    assert over.status == "ready"
    assert "current_cash_count_id" in over.evidence
    assert isinstance(over.evidence["counted_cash"], str)
    assert isinstance(over.evidence["cash_difference"], str)


def test_later_sales_recompute_ready_without_leaving_it(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-later", "900gr zanahoria")
    counted = _post(client, token, "conté 22.50", "out-later-count", "conv-out-later")
    assert counted.status_code == 200, counted.text
    ready = _outcomes(db_session, tenant.business_id)[0]
    ready_at = ready.ready_at
    changed_before = len(_audits(db_session, tenant.business_id, "outcome_run.status_changed"))
    _cash_sale(client, token, "out-later-cash", "900gr zanahoria")
    after_cash = _outcomes(db_session, tenant.business_id)[0]
    assert after_cash.id == ready.id
    assert after_cash.status == "ready"
    assert after_cash.reason_code == "ready_cash_short"
    assert after_cash.ready_at == ready_at
    assert Decimal(after_cash.evidence["expected_cash"]) > Decimal("22.50")
    changed = _audits(db_session, tenant.business_id, "outcome_run.status_changed")
    assert len(changed) == changed_before + 1
    reason_change = next(row for row in changed if row.after_payload["previous_reason_code"] == "ready_balanced")
    assert reason_change.after_payload["previous_status"] == "ready"
    assert reason_change.after_payload["status"] == "ready"
    assert reason_change.after_payload["reason_code"] == "ready_cash_short"
    assert reason_change.route_or_tool == "sale.commit@1"

    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-card", "900gr zanahoria")
    counted = _post(client, token, "conté 22.50", "out-card-count", "conv-out-card")
    assert counted.status_code == 200, counted.text
    before = _outcomes(db_session, tenant.business_id)[0]
    before_id = before.id
    before_ready_at = before.ready_at
    before_sale_count = before.evidence["sale_count"]
    before_updated_at = before.updated_at
    audits_before = len(_audits(db_session, tenant.business_id, "outcome_run.status_changed"))
    _cash_sale(client, token, "out-card-pay", "500gr tomate", method="tarjeta")
    after = _outcomes(db_session, tenant.business_id)[0]
    assert after.id == before_id
    assert after.status == "ready"
    assert after.reason_code == "ready_balanced"
    assert after.ready_at == before_ready_at
    assert after.evidence["sale_count"] == before_sale_count + 1
    assert after.evidence["cash_status"] == "balanced"
    assert after.updated_at > before_updated_at
    assert len(_audits(db_session, tenant.business_id, "outcome_run.status_changed")) == audits_before


def test_close_completes_links_snapshot_and_replay_is_quiet(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "out-close", counted="22.50")
    before_items = _all_items(db_session, tenant.business_id)
    open_item = next(row for row in before_items if row.status == "open")
    created_before = len(_audits(db_session, tenant.business_id, "work_item.created"))
    resolved_before = len(_audits(db_session, tenant.business_id, "work_item.resolved"))
    outcome_before = _outcomes(db_session, tenant.business_id)[0]
    closed = _confirm(client, token, "out-close", confirmation)
    assert closed.status_code == 200, closed.text
    run = _outcomes(db_session, tenant.business_id)[0]
    snapshot = _snapshots(db_session, tenant.business_id)[0]
    assert run.id == outcome_before.id
    assert run.status == "completed"
    assert run.reason_code == "closed_confirmed"
    assert run.completed_at is not None
    assert run.ready_at == outcome_before.ready_at
    assert run.closing_snapshot_id == snapshot.id
    assert _day(db_session, tenant.business_id).status == "closed"
    assert len(_snapshots(db_session, tenant.business_id)) == 1
    assert _open_items(db_session, tenant.business_id) == []
    linked = next(row for row in _all_items(db_session, tenant.business_id) if row.id == open_item.id)
    assert linked.status == "resolved"
    assert linked.resolution_code == "day_closed"
    assert linked.outcome_run_id == run.id
    assert len(_audits(db_session, tenant.business_id, "work_item.created")) == created_before
    assert len(_audits(db_session, tenant.business_id, "work_item.resolved")) == resolved_before + 1
    changed = _audits(db_session, tenant.business_id, "outcome_run.status_changed")
    completed_audit = next(row for row in changed if row.after_payload["status"] == "completed")
    assert completed_audit.after_payload["closing_snapshot_id"] == str(snapshot.id)
    assert completed_audit.route_or_tool == "closing.confirm@1"
    assert _count(db_session, tenant.business_id, OutboxEventRow, event_type="closing.confirmed") == 1
    assert _count(db_session, tenant.business_id, OutboxEventRow, event_type="outcome_run.completed") == 0
    replay = _confirm(client, token, "out-close", confirmation)
    assert replay.status_code == 200, replay.text
    assert len(_outcomes(db_session, tenant.business_id)) == 1
    assert len(_snapshots(db_session, tenant.business_id)) == 1
    assert len(_audits(db_session, tenant.business_id, "outcome_run.status_changed")) == len(changed)


def test_skipped_initializer_close_repairs_and_links_resolved_work(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "out-repair", counted="20.00")
    open_item = _open_items(db_session, tenant.business_id)[0]
    _forget_outcome(db_session, tenant.business_id)
    created_before = len(_audits(db_session, tenant.business_id, "work_item.created"))
    resolved_before = len(_audits(db_session, tenant.business_id, "work_item.resolved"))
    closed = _confirm(client, token, "out-repair", confirmation)
    assert closed.status_code == 200, closed.text
    run = _outcomes(db_session, tenant.business_id)[0]
    assert run.status == "completed"
    assert run.reason_code == "closed_confirmed"
    assert run.ready_at == run.completed_at
    assert run.closing_snapshot_id == _snapshots(db_session, tenant.business_id)[0].id
    linked = next(row for row in _all_items(db_session, tenant.business_id) if row.id == open_item.id)
    assert linked.outcome_run_id == run.id
    assert linked.status == "resolved"
    assert linked.resolution_code == open_item.resolution_code or linked.resolution_code == "day_closed"
    assert linked.evidence == open_item.evidence
    assert len(_audits(db_session, tenant.business_id, "work_item.created")) == created_before
    assert len(_audits(db_session, tenant.business_id, "work_item.resolved")) == resolved_before + 1
    created = _audits(db_session, tenant.business_id, "outcome_run.created")
    repair = next(row for row in created if row.after_payload["status"] == "completed")
    assert repair.after_payload["closing_snapshot_id"] == str(run.closing_snapshot_id)
    assert _open_items(db_session, tenant.business_id) == []


def test_reads_do_not_write_outcome_and_unconfirmed_sales_do_not_create_one(
    client: TestClient, db_session
) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-read", "900gr zanahoria")
    run = _outcomes(db_session, tenant.business_id)[0]
    updated_at = run.updated_at
    outcome_audits = len(_audits(db_session, tenant.business_id, "outcome_run.created")) + len(
        _audits(db_session, tenant.business_id, "outcome_run.status_changed")
    )
    prepared = _post(client, token, "preparar el cierre", "out-prep", "conv-out-read")
    summary = _post(client, token, "ventas de hoy", "out-sum", "conv-out-read")
    exported = client.get(
        "/api/v1/operational-days/current/sales-export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    nba = _nba(client, token)
    phrase = _post(client, token, "qué sigue", "out-nba", "conv-out-read")
    assert prepared.status_code == 200
    assert summary.status_code == 200
    assert exported.status_code == 200
    assert nba.status_code == 200
    assert phrase.status_code == 200
    assert nba.json()["next_best_action"]["outcome_run_id"] == str(run.id)
    assert nba.json()["next_best_action"]["title"]
    assert _outcomes(db_session, tenant.business_id)[0].updated_at == updated_at
    assert (
        len(_audits(db_session, tenant.business_id, "outcome_run.created"))
        + len(_audits(db_session, tenant.business_id, "outcome_run.status_changed"))
        == outcome_audits
    )

    _tenant_b, token_b = _seed(db_session)
    conversation = "conv-out-ready"
    added = _post(client, token_b, "900gr zanahoria", "out-rtc-add", conversation)
    totaled = _post(client, token_b, "totalizar", "out-rtc-tot", conversation)
    assert added.status_code == 200 and totaled.status_code == 200
    assert _outcomes(db_session, _tenant_b.business_id) == []
    counted = _post(client, token_b, "conté 10", "out-no-day", "conv-out-noday")
    assert counted.status_code == 200
    assert _outcomes(db_session, _tenant_b.business_id) == []


def test_tenant_cannot_read_another_business_outcome(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-tenant", "900gr zanahoria")
    own_id = _outcomes(db_session, tenant.business_id)[0].id
    other, _user, _other_token = seed_business(db_session, name="Outcome other")
    set_current_business_id(db_session, other)
    db_session.expire_all()
    hidden = db_session.scalars(select(OutcomeRunRow)).all()
    assert all(row.business_id == other for row in hidden)
    assert own_id not in {row.id for row in hidden}


def test_initializer_is_idempotent_and_skips_closed_and_older_days(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "out-init", "900gr zanahoria")
    _forget_outcome(db_session, tenant.business_id)
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(WorkItemRow.__table__.delete().where(WorkItemRow.business_id == tenant.business_id))
    db_session.execute(
        AuditEventRow.__table__.delete().where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action.in_(("outcome_run.created", "outcome_run.status_changed", "work_item.created")),
        )
    )
    older_id = new_uuid7()
    db_session.execute(
        OperationalDayRow.__table__.insert().values(
            id=older_id,
            business_id=tenant.business_id,
            business_date=date(2020, 1, 1),
            status="open",
            timezone="America/Mexico_City",
            created_at=func.now(),
            updated_at=func.now(),
        )
    )
    db_session.commit()
    admin_url = make_settings().sqlalchemy_admin_url
    assert initialize_open_today_work_items(admin_url=admin_url) >= 1
    runs = _outcomes(db_session, tenant.business_id)
    today = [row for row in runs if row.operational_day_id != older_id]
    assert len(today) == 1
    assert today[0].status == "in_progress"
    assert today[0].ready_at is None
    assert all(row.operational_day_id != older_id for row in runs)
    created = _audits(db_session, tenant.business_id, "outcome_run.created")
    assert len(created) == 1
    assert created[0].actor_id is None
    assert created[0].route_or_tool == "outcome_run.bootstrap"
    assert created[0].after_payload["origin"] == "rollout_bootstrap"
    linked = _open_items(db_session, tenant.business_id)[0]
    assert linked.outcome_run_id == today[0].id
    assert initialize_open_today_work_items(admin_url=admin_url) == 0
    assert len(_audits(db_session, tenant.business_id, "outcome_run.created")) == 1

    confirmation, _requested = _ready(client, token, "out-init-ready", counted="22.50")
    _forget_outcome(db_session, tenant.business_id)
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(WorkItemRow.__table__.delete().where(WorkItemRow.business_id == tenant.business_id))
    db_session.commit()
    initialize_open_today_work_items(admin_url=admin_url)
    ready = _outcomes(db_session, tenant.business_id)
    ready_today = [row for row in ready if row.operational_day_id != older_id]
    assert len(ready_today) == 1
    assert ready_today[0].status == "ready"
    assert ready_today[0].ready_at is not None

    closed = _confirm(client, token, "out-init-ready", confirmation)
    assert closed.status_code == 200, closed.text
    _forget_outcome(db_session, tenant.business_id)
    initialize_open_today_work_items(admin_url=admin_url)
    assert _outcomes(db_session, tenant.business_id) == []


def test_failed_parent_rolls_back_outcome(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation = "conv-out-fail"
    assert _post(client, token, "900gr zanahoria", "out-fail-add", conversation).status_code == 200
    assert _post(client, token, "totalizar", "out-fail-tot", conversation).status_code == 200
    failed = _post(
        client,
        token,
        "efectivo",
        "out-fail-pay",
        conversation,
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    assert _outcomes(db_session, tenant.business_id) == []
    assert _all_items(db_session, tenant.business_id) == []
    _cash_sale(client, token, "out-fail-ok", "900gr zanahoria")
    failed_count = _post(
        client,
        token,
        "conté 22.50",
        "out-fail-count",
        "conv-out-fail-ok",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed_count.status_code == 500
    run = _outcomes(db_session, tenant.business_id)[0]
    assert run.status == "in_progress"
    assert run.ready_at is None
    confirmation, _requested = _ready(client, token, "out-fail-close", counted="22.50")
    failed_close = _confirm(
        client,
        token,
        "out-fail-close",
        confirmation,
        key="out-fail-close-1",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed_close.status_code == 500
    assert _snapshots(db_session, tenant.business_id) == []
    survived = _outcomes(db_session, tenant.business_id)
    assert len(survived) == 1
    assert survived[0].status == "ready"
    assert survived[0].completed_at is None
    assert _day(db_session, tenant.business_id).status == "open"


def _outcomes(db_session, business_id) -> list[OutcomeRunRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(OutcomeRunRow)
            .where(OutcomeRunRow.business_id == business_id)
            .order_by(OutcomeRunRow.created_at, OutcomeRunRow.id)
        ).all()
    )


def _forget_outcome(db_session, business_id) -> None:
    set_current_business_id(db_session, business_id)
    db_session.execute(
        update(WorkItemRow)
        .where(WorkItemRow.business_id == business_id)
        .values(outcome_run_id=None)
    )
    db_session.execute(OutcomeRunRow.__table__.delete().where(OutcomeRunRow.business_id == business_id))
    db_session.commit()
