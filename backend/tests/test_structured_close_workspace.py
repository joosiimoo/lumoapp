"""Structured closing.submit_cash_count@1 and optional close_note on confirm."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.domain.operations.closing_snapshot import CLOSE_NOTE_MAX_LENGTH, normalize_close_note
from app.domain.shared.errors import ValidationAppError
from app.infrastructure.persistence.models import BusinessEventRow, ClosingSnapshotRow
from app.infrastructure.persistence.rls import set_current_business_id
from tests.isolation import seed_catalog_tenant
from tests.test_daily_close_preparation import _cash_sale, _post
from tests.test_ui_actions import _action_by_id


def _headers(token: str, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def _action(client: TestClient, token: str, conversation_id: str, action: dict, *, key: str, payload: dict | None = None):
    body = {
        "action_id": action["action_id"],
        "option_id": action.get("option_id"),
        "context_token": action["context_token"],
        "conversation_id": conversation_id,
        "idempotency_key": key,
    }
    if payload is not None:
        body["payload"] = payload
    return client.post("/api/v1/lumo/actions", headers=_headers(token, key), json=body)


def test_normalize_close_note_rules() -> None:
    assert normalize_close_note(None) is None
    assert normalize_close_note("") is None
    assert normalize_close_note("   ") is None
    assert normalize_close_note("  Faltaron dos  ") == "Faltaron dos"
    assert normalize_close_note("x" * CLOSE_NOTE_MAX_LENGTH) == "x" * CLOSE_NOTE_MAX_LENGTH
    with pytest.raises(ValidationAppError):
        normalize_close_note("x" * (CLOSE_NOTE_MAX_LENGTH + 1))
    with pytest.raises(ValidationAppError):
        normalize_close_note(12)  # type: ignore[arg-type]


def test_structured_cash_count_happy_path(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-struct-count"
    _cash_sale(client, token, "struct-sale", "900gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "struct-prep", conversation)
    assert prepared.status_code == 200, prepared.text
    card = prepared.json()["ui"][0]
    assert card["data"]["cash_status"] == "not_counted"
    action = _action_by_id(card, "closing.submit_cash_count@1")
    counted = _action(
        client,
        token,
        conversation,
        action,
        key=action["idempotency_key"],
        payload={"amount": "22.50"},
    )
    assert counted.status_code == 200, counted.text
    data = counted.json()["ui"][0]["data"]
    assert data["expected_cash"]["amount"] == "22.50"
    assert data["counted_cash"]["amount"] == "22.50"
    assert data["cash_difference"]["amount"] == "0.00"
    assert data["cash_status"] == "balanced"


def test_structured_cash_count_invalid_amount(client: TestClient, db_session) -> None:
    _tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-struct-bad"
    _cash_sale(client, token, "struct-bad-sale", "900gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "struct-bad-prep", conversation)
    action = _action_by_id(prepared.json()["ui"][0], "closing.submit_cash_count@1")
    bad = _action(
        client,
        token,
        conversation,
        action,
        key="struct-bad-amount",
        payload={"amount": "nope"},
    )
    assert bad.status_code == 200, bad.text
    assert bad.json()["ui"] == []
    assert "efectivo" in bad.json()["text"].lower() or "contaste" in bad.json()["text"].lower()


def test_structured_cash_count_replay_and_stale_token(client: TestClient, db_session) -> None:
    _tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-struct-replay"
    _cash_sale(client, token, "struct-replay-sale", "900gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "struct-replay-prep", conversation)
    action = _action_by_id(prepared.json()["ui"][0], "closing.submit_cash_count@1")
    first = _action(
        client,
        token,
        conversation,
        action,
        key=action["idempotency_key"],
        payload={"amount": "20.00"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["ui"][0]["data"]["cash_status"] == "short"
    replay = _action(
        client,
        token,
        conversation,
        action,
        key=action["idempotency_key"],
        payload={"amount": "20.00"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["text"] == first.json()["text"]
    stale = _action(
        client,
        token,
        conversation,
        {**action, "context_token": "not.a.token"},
        key="struct-stale-token",
        payload={"amount": "22.50"},
    )
    assert stale.status_code == 200, stale.text
    assert "verificar" in stale.json()["text"].lower()


def test_structured_cash_count_short_and_over(client: TestClient, db_session) -> None:
    _tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-struct-short"
    _cash_sale(client, token, "struct-short-sale", "900gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "struct-short-prep", conversation)
    action = _action_by_id(prepared.json()["ui"][0], "closing.submit_cash_count@1")
    short = _action(
        client,
        token,
        conversation,
        action,
        key="struct-short",
        payload={"amount": "20.00"},
    )
    assert short.json()["ui"][0]["data"]["cash_status"] == "short"
    assert short.json()["ui"][0]["data"]["cash_difference"]["amount"] == "-2.50"

    _tenant2, token2 = seed_catalog_tenant(db_session)
    conversation2 = "conv-struct-over"
    _cash_sale(client, token2, "struct-over-sale", "900gr zanahoria")
    prepared2 = _post(client, token2, "preparar el cierre", "struct-over-prep", conversation2)
    action2 = _action_by_id(prepared2.json()["ui"][0], "closing.submit_cash_count@1")
    over = _action(
        client,
        token2,
        conversation2,
        action2,
        key="struct-over",
        payload={"amount": "25.00"},
    )
    assert over.json()["ui"][0]["data"]["cash_status"] == "over"
    assert over.json()["ui"][0]["data"]["cash_difference"]["amount"] == "2.50"


def test_close_note_persisted_trimmed_and_rejected(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-close-note"
    _cash_sale(client, token, "note-sale", "900gr zanahoria")
    _post(client, token, "conté 22.50", "note-count", conversation)
    requested = _post(client, token, "cerrar el día", "note-request", conversation)
    confirm = _action_by_id(requested.json()["ui"][0], "closing.confirm@1")

    too_long = _action(
        client,
        token,
        conversation,
        confirm,
        key="note-too-long",
        payload={"close_note": "x" * (CLOSE_NOTE_MAX_LENGTH + 1)},
    )
    assert too_long.status_code == 200, too_long.text
    assert too_long.json()["ui"] == []
    assert "500" in too_long.json()["text"]

    blank = _action(
        client,
        token,
        conversation,
        confirm,
        key="note-blank",
        payload={"close_note": "   "},
    )
    assert blank.status_code == 200, blank.text
    assert blank.json()["ui"][0]["component"] == "daily_close_confirmed"
    assert "close_note" not in blank.json()["ui"][0]["data"]
    set_current_business_id(db_session, tenant.business_id)
    snapshot = db_session.scalars(
        select(ClosingSnapshotRow).where(ClosingSnapshotRow.business_id == tenant.business_id)
    ).one()
    assert snapshot.close_note is None
    assert snapshot.cash_status == "balanced"


def test_close_note_on_snapshot_and_memory(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-close-note-mem"
    _cash_sale(client, token, "note-mem-sale", "900gr zanahoria")
    _post(client, token, "conté 20.00", "note-mem-count", conversation)
    requested = _post(client, token, "cerrar el día", "note-mem-request", conversation)
    confirm = _action_by_id(requested.json()["ui"][0], "closing.confirm@1")
    note = "  Faltaron dos billetes  "
    confirmed = _action(
        client,
        token,
        conversation,
        confirm,
        key="note-mem-confirm",
        payload={"close_note": note},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["ui"][0]["component"] == "daily_close_confirmed"
    data = confirmed.json()["ui"][0]["data"]
    assert data["close_note"] == "Faltaron dos billetes"
    set_current_business_id(db_session, tenant.business_id)
    snapshot = db_session.scalars(
        select(ClosingSnapshotRow).where(ClosingSnapshotRow.business_id == tenant.business_id)
    ).one()
    assert snapshot.close_note == "Faltaron dos billetes"
    assert snapshot.cash_difference == Decimal("-2.50")
    event = db_session.scalars(
        select(BusinessEventRow).where(
            BusinessEventRow.business_id == tenant.business_id,
            BusinessEventRow.event_type == "daily_close_completed",
        )
    ).one()
    assert event.facts["close_note"] == "Faltaron dos billetes"


def test_close_note_null_when_omitted(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-close-note-null"
    _cash_sale(client, token, "note-null-sale", "900gr zanahoria")
    _post(client, token, "conté 22.50", "note-null-count", conversation)
    requested = _post(client, token, "cerrar el día", "note-null-request", conversation)
    confirm = _action_by_id(requested.json()["ui"][0], "closing.confirm@1")
    confirmed = _action(client, token, conversation, confirm, key="note-null-confirm")
    assert confirmed.status_code == 200, confirmed.text
    set_current_business_id(db_session, tenant.business_id)
    snapshot = db_session.scalars(
        select(ClosingSnapshotRow).where(ClosingSnapshotRow.business_id == tenant.business_id)
    ).one()
    assert snapshot.close_note is None
    event = db_session.scalars(
        select(BusinessEventRow).where(
            BusinessEventRow.business_id == tenant.business_id,
            BusinessEventRow.event_type == "daily_close_completed",
        )
    ).one()
    assert "close_note" not in event.facts


def test_stale_confirm_still_refused_with_note(client: TestClient, db_session) -> None:
    _tenant, token = seed_catalog_tenant(db_session)
    conversation = "conv-stale-note"
    _cash_sale(client, token, "stale-note-sale", "900gr zanahoria")
    _post(client, token, "conté 22.50", "stale-note-count", conversation)
    requested = _post(client, token, "cerrar el día", "stale-note-request", conversation)
    confirm = _action_by_id(requested.json()["ui"][0], "closing.confirm@1")
    _cash_sale(client, token, "stale-note-extra", "100gr zanahoria")
    stale = _action(
        client,
        token,
        conversation,
        confirm,
        key="stale-note-confirm",
        payload={"close_note": "después de otra venta"},
    )
    assert stale.status_code == 200, stale.text
    assert stale.json()["ui"][0]["component"] == "daily_close_preparation"
    assert "cambió" in stale.json()["text"].lower() or "confirma" in stale.json()["text"].lower()
