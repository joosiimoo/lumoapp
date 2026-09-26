from __future__ import annotations

from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.agent.registrations import register_conversational_sale_tools
from app.agent.tools import ToolRegistry
from app.agent.ui_actions import UiActionRegistry
from app.application.ui_action_token import issue_ui_action_token
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.models import (
    AuditEventRow,
    ClosingSnapshotRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    PaymentRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from tests.conftest import make_settings, postgres_available
from tests.test_daily_close_confirmation import _post as _message
from tests.test_daily_close_preparation import _cash_sale

pytestmark = pytest.mark.skipif(not postgres_available(make_settings()), reason="PostgreSQL is not available")

STALE = "Esta acción ya no aplica a la venta en curso."


def _auth(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def _seed(db_session):
    from tests.isolation import seed_catalog_tenant

    return seed_catalog_tenant(db_session)


def _rows(db_session, business_id, model):
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(db_session.scalars(select(model).where(model.business_id == business_id)).all())


def _ready(client, token, conversation_id: str, prefix: str):
    added = _message(client, token, "900gr zanahoria", f"{prefix}-add", conversation_id)
    assert added.status_code == 200, added.text
    totaled = _message(client, token, "totalizar", f"{prefix}-tot", conversation_id)
    assert totaled.status_code == 200, totaled.text
    card = totaled.json()["ui"][0]
    assert [action["action_id"] for action in card["actions"]] == [
        "sale.pay.cash@1",
        "sale.pay.card@1",
        "sale.pay.transfer@1",
    ]
    return card


def _pay(client, token, conversation_id: str, action: dict):
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


def _action_by_id(card: dict, action_id: str) -> dict:
    return next(action for action in card["actions"] if action["action_id"] == action_id)


def test_action_catalog_is_closed_and_not_a_tool() -> None:
    registry = UiActionRegistry()
    assert registry.ids() == [
        "sale.pay.cash@1",
        "sale.pay.card@1",
        "sale.pay.transfer@1",
        "closing.request@1",
        "closing.confirm@1",
    ]
    tools = ToolRegistry()
    register_conversational_sale_tools(tools)
    for action_id in registry.ids():
        if action_id != "closing.confirm@1":
            assert tools.get(action_id) is None
    assert tools.is_registered("closing.confirm@1")
    assert tools.is_registered("sale.pay.cash@1") is False


def test_typed_and_button_cash_each_confirm_once(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    typed_conversation = "conv-typed-cash"
    _ready(client, token, typed_conversation, "typed")
    typed = _message(client, token, "efectivo", "typed-pay", typed_conversation)
    assert typed.status_code == 200, typed.text
    assert typed.json()["ui"][0]["component"] == "sale_confirmed"
    assert typed.json()["ui"][0]["actions"] == []
    assert typed.json()["ui"][0]["data"]["payment"]["method"] == "cash"

    button_conversation = "conv-button-cash"
    card = _ready(client, token, button_conversation, "button")
    paid = _pay(client, token, button_conversation, _action_by_id(card, "sale.pay.cash@1"))
    assert paid.status_code == 200, paid.text
    assert paid.json()["ui"][0]["component"] == "sale_confirmed"
    assert paid.json()["ui"][0]["actions"] == []
    assert paid.json()["ui"][0]["data"]["payment"]["method"] == "cash"
    payments = _rows(db_session, tenant.business_id, PaymentRow)
    assert len(payments) == 2
    audits = [
        row
        for row in _rows(db_session, tenant.business_id, AuditEventRow)
        if row.action == "sale.commit@1"
    ]
    button_audit = next(row for row in audits if (row.after_payload or {}).get("ui_action_id") == "sale.pay.cash@1")
    typed_audit = next(row for row in audits if row.after_payload and "ui_action_id" not in row.after_payload)
    assert button_audit.after_payload["method"] == "cash"
    assert typed_audit.after_payload["method"] == "cash"


@pytest.mark.parametrize(
    ("action_id", "method"),
    [("sale.pay.card@1", "card"), ("sale.pay.transfer@1", "transfer")],
)
def test_card_and_transfer_buttons(client: TestClient, db_session, action_id: str, method: str) -> None:
    tenant, token = _seed(db_session)
    conversation_id = f"conv-{method}"
    card = _ready(client, token, conversation_id, method)
    claims = jwt.decode(card["actions"][0]["context_token"], options={"verify_signature": False})
    assert claims["typ"] == "ui_action"
    assert claims["sale_session_id"] == card["data"]["sale_session_id"]
    assert "payment_method" not in claims
    paid = _pay(client, token, conversation_id, _action_by_id(card, action_id))
    assert paid.status_code == 200, paid.text
    assert paid.json()["ui"][0]["data"]["payment"]["method"] == method
    assert len(_rows(db_session, tenant.business_id, PaymentRow)) == 1


def test_same_action_key_creates_one_payment(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-replay-key"
    card = _ready(client, token, conversation_id, "once")
    action = _action_by_id(card, "sale.pay.cash@1")
    first = _pay(client, token, conversation_id, action)
    second = _pay(client, token, conversation_id, action)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["ui"][0]["data"]["sale_session_id"] == first.json()["ui"][0]["data"]["sale_session_id"]
    assert len(_rows(db_session, tenant.business_id, PaymentRow)) == 1


def test_unknown_action_and_rejected_bodies_write_nothing(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-reject"
    card = _ready(client, token, conversation_id, "reject")
    action = _action_by_id(card, "sale.pay.cash@1")
    unknown = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": "sale.undo@1",
            "option_id": None,
            "context_token": action["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": "unknown-key",
        },
        headers=_auth(token, "unknown-key"),
    )
    assert unknown.status_code == 200
    assert unknown.json()["ui"] == []
    extra = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": action["action_id"],
            "option_id": None,
            "context_token": action["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": action["idempotency_key"],
            "sale_session_id": card["data"]["sale_session_id"],
        },
        headers=_auth(token, action["idempotency_key"]),
    )
    assert extra.status_code == 422
    mismatch = client.post(
        "/api/v1/lumo/actions",
        json={
            "action_id": action["action_id"],
            "option_id": None,
            "context_token": action["context_token"],
            "conversation_id": conversation_id,
            "idempotency_key": action["idempotency_key"],
        },
        headers=_auth(token, "other-key"),
    )
    assert mismatch.status_code == 422
    assert _rows(db_session, tenant.business_id, PaymentRow) == []


def test_bad_payment_tokens_write_nothing(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-token"
    card = _ready(client, token, conversation_id, "token")
    action = _action_by_id(card, "sale.pay.cash@1")
    secret = "test-dev-secret-16-chars-minimum"
    issued = utcnow()

    def post_token(context_token: str, key: str, conversation: str = conversation_id):
        return client.post(
            "/api/v1/lumo/actions",
            json={
                "action_id": "sale.pay.cash@1",
                "option_id": None,
                "context_token": context_token,
                "conversation_id": conversation,
                "idempotency_key": key,
            },
            headers=_auth(token, key),
        )

    tampered = post_token(action["context_token"][:-4] + "xxxx", "tampered")
    missing = post_token(
        issue_ui_action_token(
            secret=secret,
            action_id="sale.pay.cash@1",
            business_id=tenant.business_id,
            actor_id=tenant.actor_id,
            conversation_id=conversation_id,
            issued_at=issued,
        ),
        "missing-session",
    )
    tenant_mismatch = post_token(
        issue_ui_action_token(
            secret=secret,
            action_id="sale.pay.cash@1",
            business_id=uuid4(),
            actor_id=tenant.actor_id,
            conversation_id=conversation_id,
            issued_at=issued,
            sale_session_id=UUID(card["data"]["sale_session_id"]),
        ),
        "tenant-mismatch",
    )
    actor_mismatch = post_token(
        issue_ui_action_token(
            secret=secret,
            action_id="sale.pay.cash@1",
            business_id=tenant.business_id,
            actor_id=uuid4(),
            conversation_id=conversation_id,
            issued_at=issued,
            sale_session_id=UUID(card["data"]["sale_session_id"]),
        ),
        "actor-mismatch",
    )
    conversation_mismatch = post_token(action["context_token"], "conversation-mismatch", "conv-other")
    for response in (tampered, missing, tenant_mismatch, actor_mismatch, conversation_mismatch):
        assert response.status_code == 200, response.text
        assert response.json()["ui"] == []
        assert response.json()["text"] == "No pude verificar esa acción."
    assert _rows(db_session, tenant.business_id, PaymentRow) == []


def test_unused_old_action_is_stale_and_replay_stays_on_sale_a(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-stale-sale"
    sale_a = _ready(client, token, conversation_id, "sale-a")
    unused = _action_by_id(sale_a, "sale.pay.cash@1")
    typed = _message(client, token, "efectivo", "sale-a-typed", conversation_id)
    assert typed.status_code == 200
    added = _message(client, token, "500gr tomate", "sale-b-add", conversation_id)
    assert added.status_code == 200, added.text
    sale_b = _message(client, token, "totalizar", "sale-b-tot", conversation_id)
    assert sale_b.status_code == 200, sale_b.text
    stale = _pay(client, token, conversation_id, unused)
    assert stale.status_code == 200, stale.text
    assert stale.json()["text"] == STALE
    assert stale.json()["ui"] == []
    sessions = _rows(db_session, tenant.business_id, SaleSessionRow)
    by_id = {str(row.id): row for row in sessions}
    assert by_id[sale_a["data"]["sale_session_id"]].status == "confirmed"
    assert by_id[sale_b.json()["ui"][0]["data"]["sale_session_id"]].status == "ready_to_charge"
    payments = _rows(db_session, tenant.business_id, PaymentRow)
    assert len(payments) == 1
    assert str(payments[0].sale_session_id) == sale_a["data"]["sale_session_id"]
    assert _rows(db_session, tenant.business_id, IdempotencyRecordRow) == [
        row
        for row in _rows(db_session, tenant.business_id, IdempotencyRecordRow)
        if row.key != unused["idempotency_key"]
    ]
    stale_audits = [
        row
        for row in _rows(db_session, tenant.business_id, AuditEventRow)
        if (row.after_payload or {}).get("ui_action_id") == "sale.pay.cash@1"
    ]
    assert stale_audits == []
    before_outbox = len(_rows(db_session, tenant.business_id, OutboxEventRow))
    again = _pay(client, token, conversation_id, unused)
    assert again.json()["ui"] == []
    assert len(_rows(db_session, tenant.business_id, OutboxEventRow)) == before_outbox
    assert len(_rows(db_session, tenant.business_id, PaymentRow)) == 1

    replay_conversation = "conv-exact-replay"
    replay_card = _ready(client, token, replay_conversation, "replay")
    replay_action = _action_by_id(replay_card, "sale.pay.cash@1")
    committed = _pay(client, token, replay_conversation, replay_action)
    assert committed.json()["ui"][0]["component"] == "sale_confirmed"
    _message(client, token, "2 galletas A", "replay-b-add", replay_conversation)
    later = _message(client, token, "totalizar", "replay-b-tot", replay_conversation)
    assert later.json()["ui"][0]["data"]["status"] == "ready_to_charge"
    replayed = _pay(client, token, replay_conversation, replay_action)
    assert replayed.json()["ui"][0]["component"] == "sale_confirmed"
    assert replayed.json()["ui"][0]["data"]["sale_session_id"] == replay_card["data"]["sale_session_id"]
    later_sessions = {
        str(row.id): row.status
        for row in _rows(db_session, tenant.business_id, SaleSessionRow)
        if row.conversation_id == replay_conversation
    }
    assert later_sessions[replay_card["data"]["sale_session_id"]] == "confirmed"
    assert later_sessions[later.json()["ui"][0]["data"]["sale_session_id"]] == "ready_to_charge"


def test_confirmed_sale_without_newer_session_reads_back(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-read-back"
    card = _ready(client, token, conversation_id, "read")
    action = _action_by_id(card, "sale.pay.cash@1")
    typed = _message(client, token, "efectivo", "read-typed", conversation_id)
    assert typed.status_code == 200
    read_back = _pay(client, token, conversation_id, action)
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["ui"][0]["component"] == "sale_confirmed"
    assert read_back.json()["ui"][0]["data"]["sale_session_id"] == card["data"]["sale_session_id"]
    assert len(_rows(db_session, tenant.business_id, PaymentRow)) == 1
    keys = {row.key for row in _rows(db_session, tenant.business_id, IdempotencyRecordRow)}
    assert action["idempotency_key"] not in keys


def test_close_actions_are_two_stage(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-close-actions"
    _cash_sale(client, token, "close-act", "900gr zanahoria")
    counted = _message(client, token, "conté 22.50", "close-act-count", conversation_id)
    assert counted.status_code == 200, counted.text
    preparation = counted.json()["ui"][0]
    assert [action["action_id"] for action in preparation["actions"]] == ["closing.request@1"]
    assert preparation["data"]["confirmation_token"] is None
    requested = _pay(client, token, conversation_id, preparation["actions"][0])
    assert requested.status_code == 200, requested.text
    assert _rows(db_session, tenant.business_id, ClosingSnapshotRow) == []
    follow = requested.json()["ui"][0]
    assert [action["action_id"] for action in follow["actions"]] == ["closing.confirm@1"]
    assert follow["data"]["confirmation_token"] == follow["actions"][0]["context_token"]
    confirmed = _pay(client, token, conversation_id, follow["actions"][0])
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["ui"][0]["component"] == "daily_close_confirmed"
    assert confirmed.json()["ui"][0]["actions"] == []
    assert len(_rows(db_session, tenant.business_id, ClosingSnapshotRow)) == 1
    closed = _message(client, token, "preparar el cierre", "close-act-again", conversation_id)
    assert closed.json()["ui"][0]["actions"] == []


def test_not_counted_has_no_close_action_and_short_can_confirm(client: TestClient, db_session) -> None:
    _, token = _seed(db_session)
    conversation_id = "conv-not-counted"
    _cash_sale(client, token, "not-counted", "900gr zanahoria")
    prepared = _message(client, token, "preparar el cierre", "not-counted-prep", conversation_id)
    assert prepared.json()["ui"][0]["data"]["cash_status"] == "not_counted"
    assert prepared.json()["ui"][0]["actions"] == []

    short_conversation = "conv-short-action"
    _cash_sale(client, token, "short-act", "900gr zanahoria")
    counted = _message(client, token, "conté 10.00", "short-act-count", short_conversation)
    assert counted.json()["ui"][0]["data"]["cash_status"] == "short"
    requested = _pay(client, token, short_conversation, counted.json()["ui"][0]["actions"][0])
    assert requested.json()["ui"][0]["actions"][0]["action_id"] == "closing.confirm@1"
    confirmed = _pay(client, token, short_conversation, requested.json()["ui"][0]["actions"][0])
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["ui"][0]["data"]["cash_status"] == "short"
    assert confirmed.json()["ui"][0]["actions"] == []


def test_idempotency_rows_skip_request_close(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-request-idem"
    _cash_sale(client, token, "req-idem", "900gr zanahoria")
    counted = _message(client, token, "conté 22.50", "req-idem-count", conversation_id)
    action = counted.json()["ui"][0]["actions"][0]
    requested = _pay(client, token, conversation_id, action)
    assert requested.status_code == 200
    keys = {row.key for row in _rows(db_session, tenant.business_id, IdempotencyRecordRow)}
    assert action["idempotency_key"] not in keys
