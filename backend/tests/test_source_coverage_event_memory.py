from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent.registrations import register_conversational_sale_tools
from app.agent.tools import ToolRegistry
from app.agent.ui_actions import UiActionRegistry
from app.application.workflows.initialize_open_work_items import initialize_open_today_work_items
from app.application.workflows.outcomes import EmptyOutcomeEngine
from app.domain.operations import (
    OUTCOME_DEFINITION_ID,
    BusinessEventType,
    daily_close_ready_definition,
    recorded_operations_declaration,
)
from app.domain.operations.business_event import sale_confirmed_facts, validate_business_event_facts
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import (
    AuditEventRow,
    BusinessEventRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutcomeRunRow,
    OutboxEventRow,
    PaymentRow,
    SaleSessionRow,
    SourceCoverageRecordRow,
)
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, seed_business
from tests.test_daily_close_confirmation import _confirm, _ready
from tests.test_daily_close_preparation import _cash_sale, _post, _seed
from tests.test_ui_actions import _action_by_id, _pay, _ready as _charge_ready
from tests.test_work_items import _nba

pytestmark = pytest.mark.skipif(not __import__("tests.conftest", fromlist=["postgres_available"]).postgres_available(make_settings()), reason="PostgreSQL is not available")


def test_empty_declaration_does_not_infer_completeness() -> None:
    assert recorded_operations_declaration(()) == {
        "basis": "recorded_operations",
        "domains": [],
        "sources": [],
        "limitation_code": "only_lumo_registered_operations",
        "merchant_source_declaration": None,
    }


def test_fact_builders_reject_extra_keys() -> None:
    session_id = new_uuid7()
    facts = sale_confirmed_facts(
        sale_session_id=session_id,
        payment_id=new_uuid7(),
        payment_method="cash",
        amount="22.50",
        currency="MXN",
    )
    facts["summary"] = "all sales captured"
    with pytest.raises(ValidationAppError, match="approved keys"):
        validate_business_event_facts(
            event_type=BusinessEventType.SALE_CONFIRMED,
            source_entity_id=session_id,
            facts=facts,
        )


def test_first_confirmed_sale_records_sales_coverage_and_exact_event(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-first", "900gr zanahoria")
    coverage = _coverage(db_session, tenant.business_id)
    assert len(coverage) == 1
    row = coverage[0]
    assert row.domain == "sales"
    assert row.source_type == "manual_capture"
    assert row.status == "observed"
    assert row.limitation_code == "only_lumo_registered_operations"
    assert not hasattr(row, "updated_at") or "updated_at" not in row.__table__.columns
    events = _events(db_session, tenant.business_id)
    assert len(events) == 1
    event = events[0]
    session = _sessions(db_session, tenant.business_id)[0]
    payment = _payments(db_session, tenant.business_id)[0]
    assert event.event_type == "sale_confirmed"
    assert event.source_type == "manual_capture"
    assert event.source_entity_type == "sale_session"
    assert event.source_entity_id == session.id
    assert event.occurred_at == session.confirmed_at
    assert event.facts == {
        "sale_session_id": str(session.id),
        "payment_id": str(payment.id),
        "payment_method": "cash",
        "amount": "22.50",
        "currency": "MXN",
    }
    assert set(event.facts) == {"sale_session_id", "payment_id", "payment_method", "amount", "currency"}
    declaration = recorded_operations_declaration(_records(db_session, tenant))
    assert declaration["basis"] == "recorded_operations"
    assert declaration["domains"] == ["sales"]
    assert declaration["sources"] == ["manual_capture"]
    assert declaration["merchant_source_declaration"] is None
    assert _actions(db_session, tenant.business_id).isdisjoint(
        {"source_coverage.created", "source_coverage.updated", "business_event.created", "memory.event.created"}
    )
    assert _outbox_types(db_session, tenant.business_id).isdisjoint(
        {"memory.event.created", "source_coverage.updated"}
    )
    assert "sale.confirmed" in _outbox_types(db_session, tenant.business_id)
    assert "payment.recorded" in _outbox_types(db_session, tenant.business_id)


def test_second_sale_reuses_coverage_without_updating_it(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-second-a", "900gr zanahoria")
    first = _coverage(db_session, tenant.business_id)[0]
    _cash_sale(client, token, "cov-second-b", "900gr zanahoria")
    rows = _coverage(db_session, tenant.business_id)
    assert len(rows) == 1
    assert rows[0].id == first.id
    assert rows[0].status == "observed"
    assert rows[0].limitation_code == "only_lumo_registered_operations"
    assert rows[0].created_at == first.created_at
    assert len(_events(db_session, tenant.business_id)) == 2


def test_typed_payment_and_pay_action_share_manual_capture(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-typed", "900gr zanahoria", method="efectivo")
    card = _charge_ready(client, token, "conv-cov-action", "cov-action")
    paid = _pay(client, token, "conv-cov-action", _action_by_id(card, "sale.pay.card@1"))
    assert paid.status_code == 200, paid.text
    rows = _coverage(db_session, tenant.business_id)
    assert len(rows) == 1
    assert rows[0].domain == "sales"
    assert rows[0].source_type == "manual_capture"
    events = _events(db_session, tenant.business_id)
    assert {event.facts["payment_method"] for event in events} == {"cash", "card"}
    assert {event.source_type for event in events} == {"manual_capture"}


def test_ready_to_charge_totalize_and_replay_do_not_write_memory(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation = "conv-cov-ready"
    assert _post(client, token, "900gr zanahoria", "cov-ready-add", conversation).status_code == 200
    totaled = _post(client, token, "totalizar", "cov-ready-tot", conversation)
    assert totaled.status_code == 200, totaled.text
    assert _coverage(db_session, tenant.business_id) == []
    assert _events(db_session, tenant.business_id) == []
    paid = _post(client, token, "efectivo", "cov-ready-pay", conversation)
    assert paid.status_code == 200, paid.text
    replay = _post(client, token, "efectivo", "cov-ready-pay", conversation)
    assert replay.status_code == 200, replay.text
    assert len(_coverage(db_session, tenant.business_id)) == 1
    assert len(_events(db_session, tenant.business_id)) == 1
    assert _idempotency_types(db_session, tenant.business_id).issubset(
        {
            "lumo.message.add_sale_item",
            "lumo.message.totalize_sale",
            "lumo.message.commit_sale",
            "lumo.message.record_cash_count",
            "lumo.message.confirm_close",
        }
    )


def test_cash_count_coverage_is_reused_and_short_facts_are_exact(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-short", "900gr zanahoria")
    sales = _coverage(db_session, tenant.business_id)[0]
    short = _post(client, token, "conté 20.00", "cov-short-count", "conv-cov-short")
    assert short.status_code == 200, short.text
    rows = _coverage(db_session, tenant.business_id)
    assert {row.domain for row in rows} == {"sales", "cash_count"}
    cash = next(row for row in rows if row.domain == "cash_count")
    assert cash.source_type == "manual_capture"
    assert cash.status == "observed"
    kept = next(row for row in rows if row.domain == "sales")
    assert kept.id == sales.id
    assert kept.status == "observed"
    assert kept.created_at == sales.created_at
    cash_events = [event for event in _events(db_session, tenant.business_id) if event.event_type == "cash_count_recorded"]
    assert len(cash_events) == 1
    assert cash_events[0].source_type == "manual_capture"
    assert cash_events[0].source_entity_type == "cash_count"
    assert cash_events[0].facts == {
        "cash_count_id": str(cash_events[0].source_entity_id),
        "expected_cash": "22.50",
        "counted_cash": "20.00",
        "cash_difference": "-2.50",
        "cash_status": "short",
        "currency": "MXN",
    }
    created_at = cash.created_at
    over = _post(client, token, "conté 25.00", "cov-over-count", "conv-cov-short")
    assert over.status_code == 200, over.text
    again = _coverage(db_session, tenant.business_id)
    assert len(again) == 2
    cash_again = next(row for row in again if row.domain == "cash_count")
    assert cash_again.id == cash.id
    assert cash_again.created_at == created_at
    assert cash_again.status == "observed"
    recorded = [event for event in _events(db_session, tenant.business_id) if event.event_type == "cash_count_recorded"]
    assert len(recorded) == 2
    assert recorded[0].facts["cash_status"] == "short"
    assert recorded[0].facts["counted_cash"] == "20.00"
    assert recorded[1].facts["cash_status"] == "over"
    assert recorded[1].source_entity_id != recorded[0].source_entity_id


def test_balanced_count_and_equal_read_back_leave_sales_observed(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-bal", "900gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "cov-bal-prep", "conv-cov-bal")
    assert prepared.status_code == 200, prepared.text
    assert {row.domain for row in _coverage(db_session, tenant.business_id)} == {"sales"}
    assert [event.event_type for event in _events(db_session, tenant.business_id)] == ["sale_confirmed"]
    counted = _post(client, token, "conté 22.50", "cov-bal-count", "conv-cov-bal")
    assert counted.status_code == 200, counted.text
    sales = next(row for row in _coverage(db_session, tenant.business_id) if row.domain == "sales")
    assert sales.status == "observed"
    repeat = _post(client, token, "conté 22.50", "cov-bal-repeat", "conv-cov-bal")
    assert repeat.status_code == 200, repeat.text
    assert len([event for event in _events(db_session, tenant.business_id) if event.event_type == "cash_count_recorded"]) == 1
    assert len(_coverage(db_session, tenant.business_id)) == 2


def test_close_records_one_event_and_does_not_declare_completeness(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, requested = _ready(client, token, "cov-close", counted="20.00")
    sales_before = next(row for row in _coverage(db_session, tenant.business_id) if row.domain == "sales")
    closed = _confirm(client, token, "cov-close", confirmation, key="cov-close-1")
    assert closed.status_code == 200, closed.text
    assert closed.json()["text"].startswith("Cierre confirmado")
    rows = _coverage(db_session, tenant.business_id)
    assert {row.domain for row in rows} == {"sales", "cash_count"}
    assert "daily_close" not in {row.domain for row in rows}
    sales = next(row for row in rows if row.domain == "sales")
    assert sales.id == sales_before.id
    assert sales.status == "observed"
    assert sales.created_at == sales_before.created_at
    assert all(row.status == "observed" for row in rows)
    closes = [event for event in _events(db_session, tenant.business_id) if event.event_type == "daily_close_completed"]
    assert len(closes) == 1
    event = closes[0]
    outcome = _outcomes(db_session, tenant.business_id)[0]
    assert event.source_type == "manual_capture"
    assert event.source_entity_type == "closing_snapshot"
    assert event.facts["closing_snapshot_id"] == str(event.source_entity_id)
    assert event.facts["outcome_run_id"] == str(outcome.id)
    assert outcome.closing_snapshot_id == event.source_entity_id
    assert event.facts["sale_count"] == 1
    assert event.facts["cash_status"] == "short"
    assert event.facts["expected_cash"] == "22.50"
    assert event.facts["counted_cash"] == "20.00"
    assert event.facts["cash_difference"] == "-2.50"
    assert "summary" not in event.facts
    assert "completeness" not in event.facts
    forbidden_evidence = {"source_coverage_id", "coverage_summary", "completeness"}
    assert forbidden_evidence.isdisjoint(outcome.evidence)
    declaration = recorded_operations_declaration(_records(db_session, tenant))
    assert declaration["domains"] == ["cash_count", "sales"]
    assert declaration["sources"] == ["manual_capture"]
    assert declaration["limitation_code"] == "only_lumo_registered_operations"
    replay = _confirm(client, token, "cov-close", confirmation, key="cov-close-1")
    other = _confirm(client, token, "cov-close", confirmation, key="cov-close-2", message="confirmar")
    assert replay.status_code == 200
    assert other.status_code == 200, other.text
    assert len([event for event in _events(db_session, tenant.business_id) if event.event_type == "daily_close_completed"]) == 1
    assert requested.status_code == 200
    assert "lumo.message.confirm_close" in _idempotency_types(db_session, tenant.business_id)
    assert "closing.confirmed" in _outbox_types(db_session, tenant.business_id)


def test_clarify_stale_and_closed_day_refusal_do_not_add_events(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    invalid = _confirm(client, token, "cov-invalid", "not-a-token", key="cov-invalid-1")
    assert invalid.status_code == 200
    assert _events(db_session, tenant.business_id) == []
    confirmation, _requested = _ready(client, token, "cov-stale")
    before = len(_events(db_session, tenant.business_id))
    recounted = _post(client, token, "conté 20", "cov-stale-recount", "conv-cov-stale")
    assert recounted.status_code == 200, recounted.text
    stale = _confirm(client, token, "cov-stale", confirmation, key="cov-stale-confirm")
    assert stale.status_code == 200, stale.text
    assert not any(event.event_type == "daily_close_completed" for event in _events(db_session, tenant.business_id))
    assert len(_events(db_session, tenant.business_id)) == before + 1
    fresh, _requested_again = _ready(client, token, "cov-stale-ok", counted="20.00")
    closed = _confirm(client, token, "cov-stale-ok", fresh, key="cov-stale-ok-1")
    assert closed.status_code == 200, closed.text
    close_count = len([event for event in _events(db_session, tenant.business_id) if event.event_type == "daily_close_completed"])
    refused = _post(client, token, "900gr zanahoria", "cov-closed-add", "conv-cov-closed-sale")
    assert refused.status_code == 200
    assert len([event for event in _events(db_session, tenant.business_id) if event.event_type == "daily_close_completed"]) == close_count
    summary = _post(client, token, "ventas de hoy", "cov-sum", "conv-cov-sum")
    assert summary.status_code == 200, summary.text
    assert summary.json()["text"].startswith("Hoy")


def test_failed_parent_rolls_back_coverage_and_events(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation = "conv-cov-fail"
    assert _post(client, token, "900gr zanahoria", "cov-fail-add", conversation).status_code == 200
    assert _post(client, token, "totalizar", "cov-fail-tot", conversation).status_code == 200
    failed = _post(client, token, "efectivo", "cov-fail-pay", conversation, **{"X-Debug-Fail-After-Write": "1"})
    assert failed.status_code == 500
    assert _coverage(db_session, tenant.business_id) == []
    assert _events(db_session, tenant.business_id) == []
    _cash_sale(client, token, "cov-fail-ok", "900gr zanahoria")
    failed_count = _post(
        client,
        token,
        "conté 22.50",
        "cov-fail-count",
        "conv-cov-fail-ok",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed_count.status_code == 500
    assert {row.domain for row in _coverage(db_session, tenant.business_id)} == {"sales"}
    assert [event.event_type for event in _events(db_session, tenant.business_id)] == ["sale_confirmed"]
    confirmation, _requested = _ready(client, token, "cov-fail-close")
    before = {row.id for row in _coverage(db_session, tenant.business_id)}
    failed_close = _confirm(
        client,
        token,
        "cov-fail-close",
        confirmation,
        key="cov-fail-close-1",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed_close.status_code == 500
    assert {row.id for row in _coverage(db_session, tenant.business_id)} == before
    assert not any(event.event_type == "daily_close_completed" for event in _events(db_session, tenant.business_id))


def test_tenant_cannot_read_another_business_memory(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-tenant", "900gr zanahoria")
    own_coverage = {row.id for row in _coverage(db_session, tenant.business_id)}
    own_events = {row.id for row in _events(db_session, tenant.business_id)}
    other, _user, _other_token = seed_business(db_session, name="Coverage other")
    set_current_business_id(db_session, other)
    db_session.expire_all()
    hidden_coverage = db_session.scalars(select(SourceCoverageRecordRow)).all()
    hidden_events = db_session.scalars(select(BusinessEventRow)).all()
    assert own_coverage.isdisjoint({row.id for row in hidden_coverage})
    assert own_events.isdisjoint({row.id for row in hidden_events})
    assert all(row.business_id == other for row in hidden_coverage)
    assert all(row.business_id == other for row in hidden_events)


def test_pure_reads_and_outcome_evaluate_write_nothing(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-read", "900gr zanahoria")
    coverage_ids = [row.id for row in _coverage(db_session, tenant.business_id)]
    event_ids = [row.id for row in _events(db_session, tenant.business_id)]
    prepared = _post(client, token, "preparar el cierre", "cov-read-prep", "conv-cov-read")
    summary = _post(client, token, "ventas de hoy", "cov-read-sum", "conv-cov-read")
    exported = client.get(
        "/api/v1/operational-days/current/sales-export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    nba = _nba(client, token)
    phrase = _post(client, token, "qué sigue", "cov-read-nba", "conv-cov-read")
    engine = EmptyOutcomeEngine()
    engine.register(OUTCOME_DEFINITION_ID, daily_close_ready_definition())
    assert engine.evaluate(OUTCOME_DEFINITION_ID, {"day_status": "open", "sale_count": 1, "cash_status": None}) == "in_progress"
    assert prepared.status_code == 200
    assert summary.status_code == 200
    assert summary.json()["text"].startswith("Hoy")
    assert exported.status_code == 200
    assert nba.status_code == 200
    assert phrase.status_code == 200
    assert [row.id for row in _coverage(db_session, tenant.business_id)] == coverage_ids
    assert [row.id for row in _events(db_session, tenant.business_id)] == event_ids


def test_repository_lists_events_by_occurred_at_then_id(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-order", "900gr zanahoria")
    day_id = _sessions(db_session, tenant.business_id)[0].operational_day_id
    earlier = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    later = datetime(2026, 1, 1, 18, 0, tzinfo=UTC)
    low = UUID("00000000-0000-7000-8000-000000000001")
    high = UUID("ffffffff-ffff-7000-8000-000000000002")
    repo = OperationsRepository(db_session)
    for event_id, occurred_at in ((high, earlier), (low, earlier), (new_uuid7(), later)):
        repo.append_business_event(
            tenant=tenant,
            event=_cash_event(tenant, day_id, event_id, occurred_at),
        )
    listed = repo.list_business_events(tenant=tenant, operational_day_id=day_id)
    assert [(event.occurred_at, event.id) for event in listed] == sorted(
        ((event.occurred_at, event.id) for event in listed),
        key=lambda item: (item[0], item[1]),
    )
    same_time = [event for event in listed if event.occurred_at == earlier]
    assert [event.id for event in same_time] == [low, high]


def test_initializer_covers_open_today_only_and_inserts_no_events(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cov-init", "900gr zanahoria")
    _post(client, token, "conté 22.50", "cov-init-count", "conv-cov-init")
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(
        SourceCoverageRecordRow.__table__.delete().where(SourceCoverageRecordRow.business_id == tenant.business_id)
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
    events_before = len(_events(db_session, tenant.business_id))
    audits_before = len(_audits(db_session, tenant.business_id))
    admin_url = make_settings().sqlalchemy_admin_url
    initialize_open_today_work_items(admin_url=admin_url)
    rows = _coverage(db_session, tenant.business_id)
    assert {row.domain for row in rows} == {"sales", "cash_count"}
    assert all(row.operational_day_id != older_id for row in rows)
    assert len(_events(db_session, tenant.business_id)) == events_before
    assert len(_audits(db_session, tenant.business_id)) == audits_before
    created = {row.domain: row.created_at for row in rows}
    identities = {row.domain: row.id for row in rows}
    initialize_open_today_work_items(admin_url=admin_url)
    again = _coverage(db_session, tenant.business_id)
    assert {row.domain: row.id for row in again} == identities
    assert {row.domain: row.created_at for row in again} == created
    assert len(_events(db_session, tenant.business_id)) == events_before
    confirmation, _requested = _ready(client, token, "cov-init-close")
    closed = _confirm(client, token, "cov-init-close", confirmation, key="cov-init-close-1")
    assert closed.status_code == 200, closed.text
    events_after_close = len(_events(db_session, tenant.business_id))
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(
        SourceCoverageRecordRow.__table__.delete().where(SourceCoverageRecordRow.business_id == tenant.business_id)
    )
    db_session.commit()
    initialize_open_today_work_items(admin_url=admin_url)
    assert _coverage(db_session, tenant.business_id) == []
    assert len(_events(db_session, tenant.business_id)) == events_after_close


def test_contracts_do_not_add_memory_tools_or_copy(client: TestClient) -> None:
    registry = ToolRegistry()
    register_conversational_sale_tools(registry)
    assert registry.is_registered("memory.query_events@1") is False
    assert registry.is_registered("source_coverage.query@1") is False
    assert "memory.query_events@1" not in registry.allowed_ids()
    ui = client.app.state.generative_ui_registry
    assert ui.get("memory", 1) is None
    assert ui.get("source_coverage", 1) is None
    assert ui.get("business_event", 1) is None
    assert UiActionRegistry().ids() == [
        "sale.pay.cash@1",
        "sale.pay.card@1",
        "sale.pay.transfer@1",
        "closing.request@1",
        "closing.confirm@1",
    ]


def _coverage(db_session, business_id) -> list[SourceCoverageRecordRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(SourceCoverageRecordRow)
            .where(SourceCoverageRecordRow.business_id == business_id)
            .order_by(SourceCoverageRecordRow.domain, SourceCoverageRecordRow.id)
        ).all()
    )


def _events(db_session, business_id) -> list[BusinessEventRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(BusinessEventRow)
            .where(BusinessEventRow.business_id == business_id)
            .order_by(BusinessEventRow.occurred_at, BusinessEventRow.id)
        ).all()
    )


def _sessions(db_session, business_id) -> list[SaleSessionRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(select(SaleSessionRow).where(SaleSessionRow.business_id == business_id)).all()
    )


def _payments(db_session, business_id) -> list[PaymentRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(db_session.scalars(select(PaymentRow).where(PaymentRow.business_id == business_id)).all())


def _outcomes(db_session, business_id) -> list[OutcomeRunRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(db_session.scalars(select(OutcomeRunRow).where(OutcomeRunRow.business_id == business_id)).all())


def _records(db_session, tenant: TenantContext):
    return OperationsRepository(db_session).list_source_coverage(
        tenant=tenant,
        operational_day_id=_coverage(db_session, tenant.business_id)[0].operational_day_id,
    )


def _actions(db_session, business_id) -> set[str]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return set(
        db_session.scalars(select(AuditEventRow.action).where(AuditEventRow.business_id == business_id)).all()
    )


def _outbox_types(db_session, business_id) -> set[str]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return set(
        db_session.scalars(select(OutboxEventRow.event_type).where(OutboxEventRow.business_id == business_id)).all()
    )


def _idempotency_types(db_session, business_id) -> set[str]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return set(
        db_session.scalars(
            select(IdempotencyRecordRow.operation_type).where(IdempotencyRecordRow.business_id == business_id)
        ).all()
    )


def _audits(db_session, business_id) -> list[AuditEventRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(db_session.scalars(select(AuditEventRow).where(AuditEventRow.business_id == business_id)).all())


def _cash_event(tenant: TenantContext, day_id, event_id: UUID, occurred_at: datetime):
    from app.domain.operations.business_event import (
        BusinessEvent,
        BusinessEventSourceType,
        SourceEntityType,
        cash_count_recorded_facts,
    )

    return BusinessEvent(
        id=event_id,
        business_id=tenant.business_id,
        operational_day_id=day_id,
        event_type=BusinessEventType.CASH_COUNT_RECORDED,
        occurred_at=occurred_at,
        source_type=BusinessEventSourceType.MANUAL_CAPTURE,
        source_entity_type=SourceEntityType.CASH_COUNT,
        source_entity_id=event_id,
        facts=cash_count_recorded_facts(
            cash_count_id=event_id,
            expected_cash="1.00",
            counted_cash="1.00",
            cash_difference_amount="0.00",
            cash_status="balanced",
            currency="MXN",
        ),
        created_at=occurred_at,
    )
