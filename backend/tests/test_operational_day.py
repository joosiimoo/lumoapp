from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent.providers.scripted import ScriptedLLMProvider
from app.agent.registrations import OPERATIONAL_DAY_SUMMARY, register_conversational_sale_tools
from app.agent.tools import ToolRegistry
from app.infrastructure.persistence.models import (
    AuditEventRow,
    BusinessRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutboxEventRow,
    PaymentRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import ensure_carrota_seed
from app.policies import PolicyRequest
from app.policies.engine import DAY_001, FoundationPolicyEngine
from tests.conftest import seed_business
from tests.sale_cleanup import clear_tenant_sale_mutations


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _post(client: TestClient, token: str, message: str, key: str, conversation_id: str, **extra: str):
    return client.post(
        "/api/v1/lumo/messages",
        json={"message": message, "conversation_id": conversation_id},
        headers=_auth(token, **{"Idempotency-Key": key, **extra}),
    )


def _seed(db_session):
    tenant, token = ensure_carrota_seed(db_session, token_secret="test-dev-secret-16-chars-minimum")
    db_session.commit()
    clear_tenant_sale_mutations(db_session, tenant.business_id)
    return tenant, token


def _ready(client: TestClient, token: str, conversation_id: str, prefix: str, utterance: str) -> None:
    added = _post(client, token, utterance, f"{prefix}-add", conversation_id)
    assert added.status_code == 200, added.text
    totaled = _post(client, token, "totalizar", f"{prefix}-tot", conversation_id)
    assert totaled.status_code == 200, totaled.text


def _days(db_session, business_id):
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return db_session.scalars(select(OperationalDayRow).where(OperationalDayRow.business_id == business_id)).all()


def _sessions(db_session, business_id):
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return db_session.scalars(select(SaleSessionRow).where(SaleSessionRow.business_id == business_id)).all()


def test_closed_day_phrases_only() -> None:
    provider = ScriptedLLMProvider()
    for phrase in ("como vamos hoy", "ventas de hoy", "cuanto vendimos hoy", "¿Cómo vamos hoy?"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "day_summary"
        assert decision.candidate_tool == "operational_day.summary@1"
    for phrase in ("ventas de ayer", "ventas de la semana", "ventas de hoy por favor", "como vamos"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "unsupported"
        assert decision.candidate_tool is None


def test_day_summary_tool_is_read_only() -> None:
    registry = ToolRegistry()
    register_conversational_sale_tools(registry)
    registration = registry.get("operational_day.summary@1")
    assert registration is OPERATIONAL_DAY_SUMMARY
    assert registration is not None
    assert registration.permission == "sale.create"
    assert registration.policy_id == "DAY-001"
    assert registration.side_effect == "read"
    assert registration.requires_idempotency is False
    decision = FoundationPolicyEngine().evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="operational_day.summary@1",
            tool_registered=True,
            from_llm=True,
            arguments={"sale_count": 4, "gross_sales_total": "9.00"},
        )
    )
    assert decision.decision.value == "allow"
    assert DAY_001 in decision.rule_ids


def test_zero_summary_inserts_nothing(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    first = _post(client, token, "ventas de hoy", "day-zero-1", "conv-day-zero")
    second = _post(client, token, "como vamos hoy", "day-zero-2", "conv-day-zero")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    body = second.json()
    card = body["ui"][0]
    assert card["component"] == "operational_day_summary"
    assert card["version"] == 1
    assert card["actions"] == []
    assert card["fallback_text"] == body["text"]
    assert card["data"]["operational_day_id"] is None
    assert card["data"]["status"] is None
    assert card["data"]["sale_count"] == 0
    assert card["data"]["gross_sales_total"] == "0.00"
    assert card["data"]["cash_total"] == "0.00"
    assert card["data"]["card_total"] == "0.00"
    assert card["data"]["transfer_total"] == "0.00"
    assert _days(db_session, tenant.business_id) == []
    set_current_business_id(db_session, tenant.business_id)
    opened = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action == "operational_day.opened",
        )
    ).all()
    keys = db_session.scalars(
        select(IdempotencyRecordRow).where(IdempotencyRecordRow.key.in_(["day-zero-1", "day-zero-2"]))
    ).all()
    assert opened == []
    assert keys == []


def test_first_sale_opens_one_day_and_methods_split(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _ready(client, token, "conv-cash", "cash", "900gr zanahoria")
    cash = _post(client, token, "efectivo", "cash-pay", "conv-cash")
    assert cash.status_code == 200, cash.text
    _ready(client, token, "conv-card", "card", "500gr tomate")
    card = _post(client, token, "tarjeta", "card-pay", "conv-card")
    assert card.status_code == 200, card.text
    _ready(client, token, "conv-transfer", "xfer", "2 galletas A")
    transfer = _post(client, token, "transferencia", "xfer-pay", "conv-transfer")
    assert transfer.status_code == 200, transfer.text

    days = _days(db_session, tenant.business_id)
    assert len(days) == 1
    assert days[0].status == "open"
    sessions = _sessions(db_session, tenant.business_id)
    confirmed = [session for session in sessions if session.status == "confirmed"]
    assert len(confirmed) == 3
    assert {session.operational_day_id for session in confirmed} == {days[0].id}
    assert all(session.confirmed_at is not None for session in confirmed)
    active = [session for session in sessions if session.status != "confirmed"]
    assert all(session.operational_day_id is None and session.confirmed_at is None for session in active)

    summary = _post(client, token, "cuanto vendimos hoy", "day-sum", "conv-day-sum")
    assert summary.status_code == 200, summary.text
    data = summary.json()["ui"][0]["data"]
    assert data["operational_day_id"] == str(days[0].id)
    assert data["sale_count"] == 3
    assert data["cash_total"] == "22.50"
    assert data["card_total"] == "10.00"
    assert data["transfer_total"] == "24.00"
    assert data["gross_sales_total"] == "56.50"
    assert data["currency"] == "MXN"
    set_current_business_id(db_session, tenant.business_id)
    opened_audits = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action == "operational_day.opened",
        )
    ).all()
    opened_outbox = db_session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == tenant.business_id,
            OutboxEventRow.event_type == "operational_day.opened",
        )
    ).all()
    assert len(opened_audits) == 1
    assert len(opened_outbox) == 1
    assert opened_audits[0].after_payload["timezone"] == "America/Mexico_City"
    assert opened_outbox[0].payload["timezone"] == "America/Mexico_City"
    commit_audit = db_session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action == "sale.commit@1",
        )
    ).all()
    assert all("operational_day_id" in (row.after_payload or {}) for row in commit_audit)
    confirmed_events = db_session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == tenant.business_id,
            OutboxEventRow.event_type == "sale.confirmed",
        )
    ).all()
    assert all(event.payload.get("operational_day_id") == str(days[0].id) for event in confirmed_events)


def test_replay_and_next_sale_share_the_day(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-replay-day"
    _ready(client, token, conversation_id, "one", "900gr zanahoria")
    first = _post(client, token, "efectivo", "replay-pay", conversation_id)
    replay = _post(client, token, "efectivo", "replay-pay", conversation_id)
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["ui"][0]["data"]["payment_id"] == first.json()["ui"][0]["data"]["payment_id"]
    added = _post(client, token, "500gr tomate", "replay-next", conversation_id)
    assert added.status_code == 200, added.text
    _ready_existing = _post(client, token, "totalizar", "replay-next-tot", conversation_id)
    assert _ready_existing.status_code == 200
    second = _post(client, token, "efectivo", "replay-pay-2", conversation_id)
    assert second.status_code == 200, second.text
    days = _days(db_session, tenant.business_id)
    sessions = [session for session in _sessions(db_session, tenant.business_id) if session.status == "confirmed"]
    assert len(days) == 1
    assert len(sessions) == 2
    assert {session.conversation_id for session in sessions} == {conversation_id}
    assert {session.operational_day_id for session in sessions} == {days[0].id}
    set_current_business_id(db_session, tenant.business_id)
    opened = db_session.scalar(
        select(func.count())
        .select_from(AuditEventRow)
        .where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action == "operational_day.opened",
        )
    )
    assert opened == 1


def test_injected_clock_sets_confirmed_at_and_midnight_boundary(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    before = "2026-09-22T05:59:59+00:00"
    after = "2026-09-22T06:00:00+00:00"
    _ready(client, token, "conv-before", "before", "900gr zanahoria")
    early = _post(client, token, "efectivo", "before-pay", "conv-before", **{"X-Debug-Now": before})
    _ready(client, token, "conv-after", "after", "1kg tomate")
    late = _post(client, token, "efectivo", "after-pay", "conv-after", **{"X-Debug-Now": after})
    assert early.status_code == 200, early.text
    assert late.status_code == 200, late.text
    sessions = {session.conversation_id: session for session in _sessions(db_session, tenant.business_id)}
    assert sessions["conv-before"].confirmed_at == datetime(2026, 9, 22, 5, 59, 59, tzinfo=UTC)
    assert sessions["conv-after"].confirmed_at == datetime(2026, 9, 22, 6, 0, 0, tzinfo=UTC)
    days = {day.business_date.isoformat(): day for day in _days(db_session, tenant.business_id)}
    assert set(days) == {"2026-09-21", "2026-09-22"}
    assert sessions["conv-before"].operational_day_id == days["2026-09-21"].id
    assert sessions["conv-after"].operational_day_id == days["2026-09-22"].id


def test_invalid_timezone_rolls_back_commit(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _ready(client, token, "conv-bad-tz", "bad", "900gr zanahoria")
    set_current_business_id(db_session, tenant.business_id)
    business = db_session.get(BusinessRow, tenant.business_id)
    assert business is not None
    business.timezone = "Not/AZone"
    db_session.commit()
    try:
        failed = _post(client, token, "efectivo", "bad-pay", "conv-bad-tz")
        assert failed.status_code == 422, failed.text
        sessions = _sessions(db_session, tenant.business_id)
        assert len(sessions) == 1
        assert sessions[0].status == "ready_to_charge"
        assert sessions[0].operational_day_id is None
        assert sessions[0].confirmed_at is None
        assert _days(db_session, tenant.business_id) == []
        set_current_business_id(db_session, tenant.business_id)
        payments = db_session.scalars(select(PaymentRow).where(PaymentRow.business_id == tenant.business_id)).all()
        assert payments == []
    finally:
        set_current_business_id(db_session, tenant.business_id)
        business = db_session.get(BusinessRow, tenant.business_id)
        assert business is not None
        business.timezone = "America/Mexico_City"
        db_session.commit()


def test_first_sale_rollback_removes_the_day(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _ready(client, token, "conv-rollback-day", "rb", "900gr zanahoria")
    failed = _post(
        client,
        token,
        "efectivo",
        "rb-pay",
        "conv-rollback-day",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    sessions = _sessions(db_session, tenant.business_id)
    assert len(sessions) == 1
    assert sessions[0].status == "ready_to_charge"
    assert _days(db_session, tenant.business_id) == []


def test_later_sale_rollback_keeps_existing_day(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _ready(client, token, "conv-keep", "keep", "900gr zanahoria")
    kept = _post(client, token, "efectivo", "keep-pay", "conv-keep")
    assert kept.status_code == 200, kept.text
    day_id = _days(db_session, tenant.business_id)[0].id
    _ready(client, token, "conv-keep-2", "keep2", "500gr tomate")
    failed = _post(
        client,
        token,
        "efectivo",
        "keep2-pay",
        "conv-keep-2",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    days = _days(db_session, tenant.business_id)
    assert len(days) == 1
    assert days[0].id == day_id
    sessions = _sessions(db_session, tenant.business_id)
    confirmed = [session for session in sessions if session.status == "confirmed"]
    ready = [session for session in sessions if session.status == "ready_to_charge"]
    assert len(confirmed) == 1
    assert confirmed[0].operational_day_id == day_id
    assert len(ready) == 1
    assert ready[0].operational_day_id is None


def test_unsupported_phrase_does_not_mutate(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    response = _post(client, token, "ventas de ayer", "unsupported-day", "conv-unsupported")
    assert response.status_code == 200, response.text
    assert response.json()["ui"] == []
    assert _days(db_session, tenant.business_id) == []
    assert _sessions(db_session, tenant.business_id) == []


def test_rls_hides_other_business_days(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _ready(client, token, "conv-rls", "rls", "900gr zanahoria")
    paid = _post(client, token, "efectivo", "rls-pay", "conv-rls")
    assert paid.status_code == 200, paid.text
    other_id, _, _ = seed_business(db_session, name="Other day")
    set_current_business_id(db_session, other_id)
    db_session.expire_all()
    hidden = db_session.scalars(select(OperationalDayRow)).all()
    assert hidden == []
    visible = _days(db_session, tenant.business_id)
    assert len(visible) == 1


def test_concurrent_first_sales_share_one_day(app, db_session) -> None:
    tenant, token = _seed(db_session)
    with TestClient(app, raise_server_exceptions=False) as setup:
        _ready(setup, token, "conv-race-a", "race-a", "900gr zanahoria")
        _ready(setup, token, "conv-race-b", "race-b", "500gr tomate")

    def pay(conversation_id: str, key: str):
        with TestClient(app, raise_server_exceptions=False) as client:
            return _post(client, token, "efectivo", key, conversation_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(pay, "conv-race-a", "race-pay-a")
        second = pool.submit(pay, "conv-race-b", "race-pay-b")
        left = first.result(timeout=30)
        right = second.result(timeout=30)
    assert left.status_code == 200, left.text
    assert right.status_code == 200, right.text
    days = _days(db_session, tenant.business_id)
    confirmed = [session for session in _sessions(db_session, tenant.business_id) if session.status == "confirmed"]
    assert len(days) == 1
    assert len(confirmed) == 2
    assert {session.operational_day_id for session in confirmed} == {days[0].id}
    set_current_business_id(db_session, tenant.business_id)
    opened = db_session.scalar(
        select(func.count())
        .select_from(OutboxEventRow)
        .where(
            OutboxEventRow.business_id == tenant.business_id,
            OutboxEventRow.event_type == "operational_day.opened",
        )
    )
    assert opened == 1
