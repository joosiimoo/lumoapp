"""Sale corrections: remove item, void, sale_revision, export status, memory."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from time import sleep

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.application.workflows.get_daily_close_preparation import STALE_CONFIRMATION_TEXT
from app.infrastructure.persistence.models import (
    AuditEventRow,
    BusinessEventRow,
    CashCountRow,
    ClosingSnapshotRow,
    OperationalDayRow,
    OutboxEventRow,
    PaymentRow,
    SaleItemRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, postgres_available
from tests.test_daily_close_confirmation import _confirm as _close_confirm
from tests.test_daily_close_confirmation import _post as _message
from tests.test_daily_close_confirmation import _token_of
from tests.test_ui_actions import _action_by_id, _auth, _pay, _ready, _seed

pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")

STALE = "Esta acción ya no aplica a la venta en curso."
CONFIRMATION_STALE_TEXT = STALE_CONFIRMATION_TEXT


def _rows(db_session, business_id, model):
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(db_session.scalars(select(model).where(model.business_id == business_id)).all())


def _remove(client, token, conversation_id: str, action: dict):
    key = action["idempotency_key"]
    return client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": action["action_id"],
            "option_id": None,
            "context_token": action["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": key,
        },
        headers=_auth(token, key),
    )


def _timeline_void_request(client, token, *, sale_session_id: str | None = None) -> dict:
    response = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    for event in response.json()["events"]:
        if event.get("event_type") != "sale_confirmed":
            continue
        for action in event.get("actions") or []:
            if action.get("action_id") != "sale.void.request@1":
                continue
            claims = jwt.decode(action["context_token"], options={"verify_signature": False})
            if sale_session_id is not None and str(claims.get("sale_session_id")) != str(sale_session_id):
                continue
            assert action.get("conversation_id")
            assert action["conversation_id"] == claims["conversation_id"]
            return action
    raise AssertionError("expected timeline sale.void.request@1")


def _void_confirm_action(client, token, conversation_id: str, confirmed_card: dict | None = None) -> dict:
    sale_session_id = None if confirmed_card is None else confirmed_card.get("data", {}).get("sale_session_id")
    request = _timeline_void_request(client, token, sale_session_id=sale_session_id)
    assert request["conversation_id"] == conversation_id
    impact = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": request["action_id"],
            "option_id": None,
            "context_token": request["context_token"],
            "conversation_id": request["conversation_id"],
            "idempotency_key": request["idempotency_key"],
        },
        headers=_auth(token, request["idempotency_key"]),
    )
    assert impact.status_code == 200, impact.text
    impact_card = impact.json()["ui"][0]
    assert impact_card["component"] == "sale_confirmed"
    assert "impact" in impact_card["data"]
    return _action_by_id(impact_card, "sale.void.confirm@1")


def _void_with(client, token, conversation_id: str, confirm: dict, *, key: str, reason: str = "cobro duplicado"):
    return client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": confirm["action_id"],
            "option_id": None,
            "context_token": confirm["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": key,
            "payload": {"void_reason": reason},
        },
        headers=_auth(token, key),
    )


def _day(db_session, business_id) -> OperationalDayRow:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return db_session.scalars(
        select(OperationalDayRow).where(OperationalDayRow.business_id == business_id)
    ).one()


def _snapshots(db_session, business_id) -> list[ClosingSnapshotRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(ClosingSnapshotRow).where(ClosingSnapshotRow.business_id == business_id)
        ).all()
    )


def test_remove_one_item_from_open_keeps_revision(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-remove-open"
    first = _message(client, token, "900gr zanahoria", "rm-open-1", conversation_id)
    assert first.status_code == 200, first.text
    second = _message(client, token, "900gr zanahoria", "rm-open-2", conversation_id)
    assert second.status_code == 200, second.text
    card = second.json()["ui"][0]
    remove = _action_by_id(card, "sale.remove_item@1")
    response = _remove(client, token, conversation_id, remove)
    assert response.status_code == 200, response.text
    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    assert len(sessions) == 1
    assert sessions[0].status == "open"
    assert sessions[0].sale_revision == 1
    assert len(_rows(db_session, tenant.business_id, SaleItemRow)) == 1
    assert _rows(db_session, tenant.business_id, BusinessEventRow) == []


def test_ready_to_charge_remove_advances_revision_and_stales_old_pay(
    client: TestClient, db_session
) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-remove-rtc"
    _message(client, token, "900gr zanahoria", "rm-rtc-1", conversation_id)
    _message(client, token, "900gr zanahoria", "rm-rtc-2", conversation_id)
    totaled = _message(client, token, "totalizar", "rm-rtc-tot", conversation_id)
    assert totaled.status_code == 200, totaled.text
    card = totaled.json()["ui"][0]
    old_pay = _action_by_id(card, "sale.pay.cash@1")
    claims = jwt.decode(old_pay["context_token"], options={"verify_signature": False})
    assert claims["sale_revision"] == 1
    remove = next(a for a in card["actions"] if a["action_id"] == "sale.remove_item@1")
    removed = _remove(client, token, conversation_id, remove)
    assert removed.status_code == 200, removed.text
    body = removed.json()
    assert body["ui"][0]["component"] == "sale_summary"
    fresh_pay = _action_by_id(body["ui"][0], "sale.pay.cash@1")
    fresh_claims = jwt.decode(fresh_pay["context_token"], options={"verify_signature": False})
    assert fresh_claims["sale_revision"] == 2
    stale = _pay(client, token, conversation_id, old_pay)
    assert stale.status_code == 200, stale.text
    assert stale.json()["text"] == STALE
    assert stale.json()["ui"] == []
    assert _rows(db_session, tenant.business_id, PaymentRow) == []
    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    assert sessions[0].status == "ready_to_charge"
    assert sessions[0].sale_revision == 2
    paid = _pay(client, token, conversation_id, fresh_pay)
    assert paid.status_code == 200, paid.text
    assert paid.json()["ui"][0]["component"] == "sale_confirmed"
    payments = _rows(db_session, tenant.business_id, PaymentRow)
    assert len(payments) == 1
    assert payments[0].amount == Decimal("25.00") or payments[0].amount == Decimal("22.50")


def test_empty_ready_to_charge_remove_demotes_to_open(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-remove-empty"
    card = _ready(client, token, conversation_id, "rm-empty")
    remove = _action_by_id(card, "sale.remove_item@1")
    response = _remove(client, token, conversation_id, remove)
    assert response.status_code == 200, response.text
    assert response.json()["ui"] == []
    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    assert sessions[0].status == "open"
    assert sessions[0].sale_revision == 2
    assert _rows(db_session, tenant.business_id, SaleItemRow) == []
    assert "sale.pay.cash@1" not in response.json()["text"]


def test_void_confirmed_open_day_and_read_back(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-void"
    card = _ready(client, token, conversation_id, "void")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    confirmed = paid.json()["ui"][0]
    assert confirmed["data"]["status"] == "confirmed"
    assert not any(a["action_id"] == "sale.void.request@1" for a in confirmed.get("actions") or [])
    confirm = _void_confirm_action(client, token, conversation_id, confirmed)
    voided = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": confirm["action_id"],
            "option_id": None,
            "context_token": confirm["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": confirm["idempotency_key"],
            "payload": {"void_reason": "cobro duplicado"},
        },
        headers=_auth(token, confirm["idempotency_key"]),
    )
    assert voided.status_code == 200, voided.text
    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    assert sessions[0].status == "voided"
    assert sessions[0].void_reason == "cobro duplicado"
    assert sessions[0].voided_at is not None
    assert sessions[0].voided_by_actor_id == tenant.actor_id
    assert sessions[0].operational_day_id is not None
    assert sessions[0].confirmed_at is not None
    assert len(_rows(db_session, tenant.business_id, SaleItemRow)) == 1
    assert len(_rows(db_session, tenant.business_id, PaymentRow)) == 1
    events = _rows(db_session, tenant.business_id, BusinessEventRow)
    types = sorted(event.event_type for event in events)
    assert types == ["sale_confirmed", "sale_voided"]
    void_events = [event for event in events if event.event_type == "sale_voided"]
    assert void_events[0].facts["void_reason"] == "cobro duplicado"

    # Already voided read-back: no second event/audit/outbox
    audits_before = len(
        [row for row in _rows(db_session, tenant.business_id, AuditEventRow) if row.action == "sale.void@1"]
    )
    outbox_before = len(
        [row for row in _rows(db_session, tenant.business_id, OutboxEventRow) if row.event_type == "sale.voided"]
    )
    key = "void-readback-2"
    again = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": confirm["action_id"],
            "option_id": None,
            "context_token": confirm["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": key,
            "payload": {"void_reason": "otra vez"},
        },
        headers=_auth(token, key),
    )
    assert again.status_code == 200, again.text
    assert again.json()["ui"][0]["data"]["status"] == "voided"
    events_after = _rows(db_session, tenant.business_id, BusinessEventRow)
    assert len([e for e in events_after if e.event_type == "sale_voided"]) == 1
    assert (
        len([row for row in _rows(db_session, tenant.business_id, AuditEventRow) if row.action == "sale.void@1"])
        == audits_before
    )
    assert (
        len([row for row in _rows(db_session, tenant.business_id, OutboxEventRow) if row.event_type == "sale.voided"])
        == outbox_before
    )

def test_void_excludes_from_aggregates_and_preserves_cash_count(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-void-agg"
    card = _ready(client, token, conversation_id, "void-agg")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    counted = _message(client, token, "conté 22.50", "void-agg-count", conversation_id)
    assert counted.status_code == 200, counted.text
    cash_before = _rows(db_session, tenant.business_id, CashCountRow)
    assert cash_before
    counted_amount = cash_before[-1].amount
    confirmed = paid.json()["ui"][0]
    confirm = _void_confirm_action(client, token, conversation_id, confirmed)
    key = confirm["idempotency_key"]
    voided = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": confirm["action_id"],
            "option_id": None,
            "context_token": confirm["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": key,
            "payload": {"void_reason": "error de cobro"},
        },
        headers=_auth(token, key),
    )
    assert voided.status_code == 200, voided.text
    cash_after = _rows(db_session, tenant.business_id, CashCountRow)
    assert cash_after[-1].amount == counted_amount
    stream = client.get("/api/v1/business-stream/today", headers={"Authorization": f"Bearer {token}"})
    assert stream.status_code == 200, stream.text
    body = stream.json()
    facts = body["factual_summary"]
    assert facts["sale_count"] == 0
    assert facts["gross_sales_total"]["amount"] == "0.00"
    assert facts["expected_cash"]["amount"] == "0.00"
    assert facts["counted_cash"]["amount"] == "22.50"
    assert facts["cash_difference"]["amount"] == "22.50"
    assert facts["cash_status"] == "over"
    # Balanced / ready_to_close must not survive after expected cash drops.
    assert body["operator_state"] != "ready_to_close"


def test_void_stales_pre_minted_closing_confirm_token(client: TestClient, db_session) -> None:
    """Direct fingerprint path: mint closing.confirm@1, void, post old token → confirmation_stale."""
    tenant, token = _seed(db_session)
    conversation_id = "conv-void-stale-close"
    card = _ready(client, token, conversation_id, "void-stale")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    confirmed = paid.json()["ui"][0]
    counted = _message(client, token, "conté 22.50", "void-stale-count", conversation_id)
    assert counted.status_code == 200, counted.text
    requested = _message(client, token, "cerrar el día", "void-stale-req", conversation_id)
    assert requested.status_code == 200, requested.text
    old_token = _token_of(requested)
    assert old_token
    assert requested.json()["ui"][0]["data"]["cash_status"] == "balanced"
    assert requested.json()["ui"][0]["data"]["cash_difference"]["amount"] == "0.00"

    confirm = _void_confirm_action(client, token, conversation_id, confirmed)
    voided = _void_with(client, token, conversation_id, confirm, key=confirm["idempotency_key"])
    assert voided.status_code == 200, voided.text
    assert voided.json()["ui"][0]["data"]["status"] == "voided"

    stale = _close_confirm(client, token, "void-stale", old_token, key="void-stale-confirm")
    assert stale.status_code == 200, stale.text
    assert stale.json()["text"] == CONFIRMATION_STALE_TEXT
    # confirmation_stale: refreshed preparation, no snapshot, day stays open.
    refreshed = _token_of(stale)
    assert refreshed and refreshed != old_token
    assert stale.json()["ui"][0]["component"] == "daily_close_preparation"
    assert stale.json()["ui"][0]["data"]["cash_difference"]["amount"] == "22.50"
    assert stale.json()["ui"][0]["data"]["cash_status"] == "over"
    assert stale.json()["ui"][0]["data"]["expected_cash"]["amount"] == "0.00"
    assert stale.json()["ui"][0]["data"]["counted_cash"]["amount"] == "22.50"
    assert _snapshots(db_session, tenant.business_id) == []
    assert _day(db_session, tenant.business_id).status == "open"

    stream = client.get("/api/v1/business-stream/today", headers={"Authorization": f"Bearer {token}"})
    assert stream.status_code == 200, stream.text
    facts = stream.json()["factual_summary"]
    assert facts["sale_count"] == 0
    assert facts["expected_cash"]["amount"] == "0.00"
    assert facts["cash_difference"]["amount"] == "22.50"
    assert facts["cash_status"] == "over"


def test_concurrent_void_one_transition(app, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-void-race"
    with TestClient(app, raise_server_exceptions=False) as setup:
        card = _ready(setup, token, conversation_id, "void-race")
        paid = _pay(setup, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
        assert paid.status_code == 200, paid.text
        confirm = _void_confirm_action(setup, token, conversation_id, paid.json()["ui"][0])

    def void_once(key: str):
        with TestClient(app, raise_server_exceptions=False) as local:
            return _void_with(local, token, conversation_id, confirm, key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(void_once, "void-race-a")
        right = pool.submit(void_once, "void-race-b")
        first = left.result(timeout=30)
        second = right.result(timeout=30)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["ui"][0]["data"]["status"] == "voided"
    assert second.json()["ui"][0]["data"]["status"] == "voided"

    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    assert len(sessions) == 1
    assert sessions[0].status == "voided"
    events = _rows(db_session, tenant.business_id, BusinessEventRow)
    assert len([e for e in events if e.event_type == "sale_voided"]) == 1
    assert len([e for e in events if e.event_type == "sale_confirmed"]) == 1
    assert (
        len([row for row in _rows(db_session, tenant.business_id, AuditEventRow) if row.action == "sale.void@1"])
        == 1
    )
    assert (
        len([row for row in _rows(db_session, tenant.business_id, OutboxEventRow) if row.event_type == "sale.voided"])
        == 1
    )
    assert len(_rows(db_session, tenant.business_id, PaymentRow)) == 1


def test_remove_refused_on_confirmed_and_voided(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-rm-confirmed"
    card = _ready(client, token, conversation_id, "rm-conf")
    remove = _action_by_id(card, "sale.remove_item@1")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    refused = _remove(client, token, conversation_id, remove)
    assert refused.status_code == 200, refused.text
    assert refused.json()["ui"] == []
    assert "confirmada" in refused.json()["text"].lower() or "anulada" in refused.json()["text"].lower() or "aplica" in refused.json()["text"].lower()
    assert _rows(db_session, tenant.business_id, SaleItemRow)
    assert _rows(db_session, tenant.business_id, SaleSessionRow)[0].status == "confirmed"

    confirm = _void_confirm_action(client, token, conversation_id, paid.json()["ui"][0])
    voided = _void_with(client, token, conversation_id, confirm, key="rm-void-1")
    assert voided.status_code == 200, voided.text
    refused_voided = _remove(client, token, conversation_id, remove)
    assert refused_voided.status_code == 200, refused_voided.text
    assert refused_voided.json()["ui"] == []
    assert _rows(db_session, tenant.business_id, SaleSessionRow)[0].status == "voided"
    assert len(_rows(db_session, tenant.business_id, SaleItemRow)) == 1


def test_void_refused_when_not_confirmed(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-void-open"
    card = _ready(client, token, conversation_id, "void-open")
    # Forge a void.request against the ready_to_charge session using its session id from a pay token.
    pay = _action_by_id(card, "sale.pay.cash@1")
    claims = jwt.decode(pay["context_token"], options={"verify_signature": False})
    from app.application.ui_action_token import issue_ui_action_token
    from app.infrastructure.persistence.base import utcnow
    from uuid import UUID

    token_text = issue_ui_action_token(
        secret="test-dev-secret-16-chars-minimum",
        action_id="sale.void.request@1",
        business_id=UUID(claims["business_id"]),
        actor_id=UUID(claims["actor_id"]),
        conversation_id=conversation_id,
        issued_at=utcnow(),
        sale_session_id=UUID(claims["sale_session_id"]),
    )
    response = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": "sale.void.request@1",
            "option_id": None,
            "context_token": token_text,
            "conversation_id": conversation_id,
            "idempotency_key": "void-open-1",
        },
        headers=_auth(token, "void-open-1"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["ui"] == []
    assert _rows(db_session, tenant.business_id, SaleSessionRow)[0].status == "ready_to_charge"


def test_void_refused_on_closed_day(client: TestClient, db_session) -> None:
    from tests.test_daily_close_confirmation import _ready as _close_ready, _confirm as _close_confirm

    tenant, token = _seed(db_session)
    confirmation, _requested = _close_ready(client, token, "void-closed")
    closed = _close_confirm(client, token, "void-closed", confirmation)
    assert closed.status_code == 200, closed.text
    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    assert sessions[0].status == "confirmed"
    # After close, void must refuse without mutating.
    from app.application.ui_action_token import issue_ui_action_token
    from app.infrastructure.persistence.base import utcnow

    token_text = issue_ui_action_token(
        secret="test-dev-secret-16-chars-minimum",
        action_id="sale.void.confirm@1",
        business_id=tenant.business_id,
        actor_id=tenant.actor_id,
        conversation_id="conv-void-closed",
        issued_at=utcnow(),
        sale_session_id=sessions[0].id,
    )
    refused = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": "sale.void.confirm@1",
            "option_id": None,
            "context_token": token_text,
            "conversation_id": "conv-void-closed",
            "idempotency_key": "void-closed-1",
            "payload": {"void_reason": "tarde"},
        },
        headers=_auth(token, "void-closed-1"),
    )
    assert refused.status_code == 200, refused.text
    assert refused.json()["ui"] == []
    assert "cerrada" in refused.json()["text"].lower()
    assert _rows(db_session, tenant.business_id, SaleSessionRow)[0].status == "confirmed"
    assert _rows(db_session, tenant.business_id, BusinessEventRow)
    assert "sale_voided" not in {e.event_type for e in _rows(db_session, tenant.business_id, BusinessEventRow)}


def test_export_includes_voided_with_sale_status(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-void-export"
    card = _ready(client, token, conversation_id, "void-export")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    confirmed = paid.json()["ui"][0]
    confirm = _void_confirm_action(client, token, conversation_id, confirmed)
    key = confirm["idempotency_key"]
    client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": confirm["action_id"],
            "option_id": None,
            "context_token": confirm["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": key,
            "payload": {"void_reason": "export check"},
        },
        headers=_auth(token, key),
    )
    export = client.get(
        "/api/v1/operational-days/current/sales-export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert export.status_code == 200, export.text
    lines = export.text.strip().splitlines()
    assert "sale_status" in lines[0]
    assert any(",voided," in line for line in lines[1:])


def test_timeline_void_request_eligibility_and_remint(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-mem-void"
    card = _ready(client, token, conversation_id, "mem-void")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    session_id = paid.json()["ui"][0]["data"]["sale_session_id"]
    assert not any(
        a["action_id"] == "sale.void.request@1" for a in paid.json()["ui"][0].get("actions") or []
    )

    first = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {token}"})
    assert first.status_code == 200, first.text
    sale_events = [e for e in first.json()["events"] if e["event_type"] == "sale_confirmed"]
    assert len(sale_events) == 1
    actions = sale_events[0].get("actions") or []
    assert len(actions) == 1
    assert actions[0]["action_id"] == "sale.void.request@1"
    assert actions[0]["conversation_id"] == conversation_id
    claims = jwt.decode(actions[0]["context_token"], options={"verify_signature": False})
    assert claims["typ"] == "ui_action"
    assert claims["action_id"] == "sale.void.request@1"
    assert str(claims["sale_session_id"]) == str(session_id)
    assert claims["conversation_id"] == conversation_id
    assert str(claims["business_id"]) == str(tenant.business_id)

    for event in first.json()["events"]:
        if event["event_type"] != "sale_confirmed":
            assert not (event.get("actions") or [])

    sleep(1.1)  # JWT iat is second-resolution; remint must issue a new token.
    second = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {token}"})
    assert second.status_code == 200, second.text
    reminted = next(
        a
        for e in second.json()["events"]
        if e["event_type"] == "sale_confirmed"
        for a in (e.get("actions") or [])
        if a["action_id"] == "sale.void.request@1"
    )
    assert reminted["idempotency_key"] != actions[0]["idempotency_key"]
    assert reminted["context_token"] != actions[0]["context_token"]
    assert reminted["conversation_id"] == conversation_id

    confirm = _void_confirm_action(client, token, conversation_id, paid.json()["ui"][0])
    voided = _void_with(client, token, conversation_id, confirm, key=confirm["idempotency_key"])
    assert voided.status_code == 200, voided.text

    after = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 200, after.text
    types = {e["event_type"] for e in after.json()["events"]}
    assert "sale_confirmed" in types
    assert "sale_voided" in types
    for event in after.json()["events"]:
        assert not any(a.get("action_id") == "sale.void.request@1" for a in event.get("actions") or [])


def test_inicio_sale_confirmed_has_no_void_request(client: TestClient, db_session) -> None:
    _tenant, token = _seed(db_session)
    conversation_id = "conv-inicio-no-void"
    card = _ready(client, token, conversation_id, "inicio-no-void")
    paid = _pay(client, token, conversation_id, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    confirmed = paid.json()["ui"][0]
    assert confirmed["component"] == "sale_confirmed"
    assert confirmed["data"]["status"] == "confirmed"
    assert confirmed.get("actions") in ([], None) or not any(
        a["action_id"].startswith("sale.void.") for a in confirmed["actions"]
    )


def test_timeline_void_omitted_on_closed_day(client: TestClient, db_session) -> None:
    from tests.test_daily_close_confirmation import _ready as _close_ready
    from tests.test_daily_close_confirmation import _confirm as _close_confirm

    _tenant, token = _seed(db_session)
    confirmation, _requested = _close_ready(client, token, "mem-void-closed")
    closed = _close_confirm(client, token, "mem-void-closed", confirmation)
    assert closed.status_code == 200, closed.text
    assert _day(db_session, _tenant.business_id).status == "closed"

    timeline = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {token}"})
    assert timeline.status_code == 200, timeline.text
    sale_events = [e for e in timeline.json()["events"] if e["event_type"] == "sale_confirmed"]
    assert sale_events
    for event in sale_events:
        assert not any(a.get("action_id") == "sale.void.request@1" for a in event.get("actions") or [])


def test_sale_corrections_migration_constraints(db_session) -> None:
    bind = db_session.get_bind()
    with bind.connect() as connection:
        revision = connection.execute(
            text(
                """
                SELECT column_default FROM information_schema.columns
                WHERE table_schema='sales' AND table_name='sale_sessions' AND column_name='sale_revision'
                """
            )
        ).scalar()
        assert revision is not None
        row = connection.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conname IN (
                    'ck_sale_sessions_sale_revision',
                    'ck_sale_sessions_void_metadata',
                    'ck_business_events_shape'
                )
                """
            )
        ).fetchall()
        names = {r[0] for r in row}
        assert "ck_sale_sessions_sale_revision" in names
        assert "ck_sale_sessions_void_metadata" in names
        assert "ck_business_events_shape" in names
        shape = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_business_events_shape'
                """
            )
        ).scalar()
        assert shape is not None
        assert "sale_voided" in shape
