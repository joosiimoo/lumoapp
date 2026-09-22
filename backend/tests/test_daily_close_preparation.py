from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import IntegrityError

from app.agent.registrations import (
    CLOSING_PREPARE,
    DAILY_CLOSE_PREPARATION_UI,
    SUBMIT_CASH_COUNT,
    register_conversational_sale_tools,
)
from app.agent.tools import ToolRegistry
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.models import (
    AuditEventRow,
    CashCountRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutboxEventRow,
    PaymentRow,
    SaleItemRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import ensure_carrota_seed
from tests.conftest import seed_business
from tests.sale_cleanup import clear_tenant_sale_mutations, sale_integrity_orphans


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


def _cash_sale(client: TestClient, token: str, prefix: str, utterance: str, method: str = "efectivo") -> None:
    conversation_id = f"conv-{prefix}"
    added = _post(client, token, utterance, f"{prefix}-add", conversation_id)
    assert added.status_code == 200, added.text
    totaled = _post(client, token, "totalizar", f"{prefix}-tot", conversation_id)
    assert totaled.status_code == 200, totaled.text
    paid = _post(client, token, method, f"{prefix}-pay", conversation_id)
    assert paid.status_code == 200, paid.text


def _counts(db_session, business_id) -> list[CashCountRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(CashCountRow)
            .where(CashCountRow.business_id == business_id)
            .order_by(CashCountRow.counted_at, CashCountRow.id)
        ).all()
    )


def _rows(db_session, business_id, model, **where) -> list:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    stmt = select(model).where(model.business_id == business_id)
    for column, value in where.items():
        stmt = stmt.where(getattr(model, column) == value)
    return list(db_session.scalars(stmt).all())


def _card(response) -> dict:
    body = response.json()
    assert len(body["ui"]) == 1, body
    card = body["ui"][0]
    assert card["component"] == "daily_close_preparation"
    assert card["version"] == 1
    assert card["actions"] == []
    assert card["fallback_text"] == body["text"]
    return card["data"]


def test_no_day_preparation_and_count_write_nothing(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    prepared = _post(client, token, "preparar el cierre", "prep-none", "conv-close")
    assert prepared.status_code == 200, prepared.text
    data = _card(prepared)
    assert data["operational_day_id"] is None
    assert data["day_status"] is None
    assert data["sale_count"] == 0
    assert data["expected_cash"] == {"amount": "0.00", "currency": "MXN"}
    assert data["counted_cash"] is None
    assert data["cash_difference"] is None
    assert data["cash_status"] == "not_counted"
    assert data["cash_count_id"] is None
    assert "Falta contar efectivo" in prepared.json()["text"]

    counted = _post(client, token, "tengo 120 en caja", "count-none", "conv-close")
    assert counted.status_code == 200, counted.text
    assert counted.json()["ui"] == []
    assert "no hay ventas registradas hoy" in counted.json()["text"].lower()

    assert _counts(db_session, tenant.business_id) == []
    assert _rows(db_session, tenant.business_id, OperationalDayRow) == []
    assert _rows(db_session, tenant.business_id, AuditEventRow, action="closing.submit_cash_count@1") == []
    assert _rows(db_session, tenant.business_id, OutboxEventRow, event_type="cash_count.recorded") == []
    assert (
        _rows(
            db_session,
            tenant.business_id,
            IdempotencyRecordRow,
            operation_type="lumo.message.record_cash_count",
        )
        == []
    )
    repeated = _post(client, token, "preparar el cierre", "prep-none-2", "conv-close")
    assert _card(repeated) == data
    assert _rows(db_session, tenant.business_id, OperationalDayRow) == []


def test_expected_cash_without_a_count(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "prep-nc", "conv-close")
    data = _card(prepared)
    assert data["expected_cash"] == {"amount": "22.50", "currency": "MXN"}
    assert data["counted_cash"] is None
    assert data["cash_difference"] is None
    assert data["cash_status"] == "not_counted"
    assert data["sale_count"] == 1
    assert data["day_status"] == "open"
    assert _counts(db_session, tenant.business_id) == []


@pytest.mark.parametrize(
    ("utterance", "difference", "status", "word"),
    [
        ("conté 22.50", "0.00", "balanced", "Caja cuadrada"),
        ("tengo 20 en caja", "-2.50", "short", "Faltante"),
        ("tengo 25 en caja", "2.50", "over", "Sobrante"),
    ],
)
def test_balanced_shortage_and_overage(
    client: TestClient,
    db_session,
    utterance: str,
    difference: str,
    status: str,
    word: str,
) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    counted = _post(client, token, utterance, f"count-{status}", "conv-close")
    assert counted.status_code == 200, counted.text
    data = _card(counted)
    assert data["expected_cash"]["amount"] == "22.50"
    assert data["cash_difference"] == {"amount": difference, "currency": "MXN"}
    assert data["cash_status"] == status
    assert word in counted.json()["text"]
    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 1
    assert rows[0].source == "manual_capture"
    assert rows[0].currency == "MXN"
    assert rows[0].supersedes_cash_count_id is None
    assert rows[0].superseded_by_id is None
    assert rows[0].actor_id == tenant.actor_id
    day = _rows(db_session, tenant.business_id, OperationalDayRow)[0]
    assert day.status == "open"
    assert rows[0].operational_day_id == day.id
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_card_and_transfer_do_not_change_expected_cash(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    _cash_sale(client, token, "card", "500gr tomate", method="tarjeta")
    _cash_sale(client, token, "xfer", "2 galletas A", method="transferencia")
    summary = _post(client, token, "ventas de hoy", "iso-sum", "conv-close")
    summary_data = summary.json()["ui"][0]["data"]
    prepared = _post(client, token, "preparar el cierre", "iso-prep", "conv-close")
    data = _card(prepared)
    assert summary_data["cash_total"] == "22.50"
    assert summary_data["card_total"] == "10.00"
    assert summary_data["transfer_total"] == "24.00"
    assert data["expected_cash"]["amount"] == summary_data["cash_total"]
    assert data["sale_count"] == 3
    assert "gross_sales_total" not in data
    assert "card_total" not in data
    assert "transfer_total" not in data
    assert _counts(db_session, tenant.business_id) == []


def test_recount_supersedes_and_keeps_history(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    first = _post(client, token, "tengo 20 en caja", "rc-1", "conv-close")
    assert _card(first)["cash_status"] == "short"
    second = _post(client, token, "conté 22.50", "rc-2", "conv-close")
    data = _card(second)
    assert data["cash_status"] == "balanced"
    assert data["cash_difference"]["amount"] == "0.00"

    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 2
    previous, current = rows
    assert previous.amount == Decimal("20.00")
    assert current.amount == Decimal("22.50")
    assert previous.superseded_by_id == current.id
    assert current.supersedes_cash_count_id == previous.id
    assert current.superseded_by_id is None
    assert data["cash_count_id"] == str(current.id)
    assert second.json()["ui"][0]["data"].get("supersedes_cash_count_id") is None
    assert len([row for row in rows if row.superseded_by_id is None]) == 1
    audits = _rows(db_session, tenant.business_id, AuditEventRow, action="closing.submit_cash_count@1")
    events = _rows(db_session, tenant.business_id, OutboxEventRow, event_type="cash_count.recorded")
    assert len(audits) == 2
    assert len(events) == 2
    superseding = [row for row in audits if row.before_payload is not None]
    assert len(superseding) == 1
    assert superseding[0].before_payload == {"cash_count_id": str(previous.id), "amount": "20.00"}
    assert superseding[0].after_payload["supersedes_cash_count_id"] == str(previous.id)
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_recount_updates_before_it_inserts(app, db_session) -> None:
    tenant, token = _seed(db_session)
    statements: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        lowered = " ".join(statement.split()).lower()
        if "operations.cash_counts" not in lowered:
            return
        if lowered.startswith("update"):
            statements.append("update")
        elif lowered.startswith("insert"):
            statements.append("insert")

    with TestClient(app, raise_server_exceptions=False) as client:
        _cash_sale(client, token, "cash", "900gr zanahoria")
        first = _post(client, token, "tengo 20 en caja", "order-1", "conv-close")
        assert first.status_code == 200, first.text
        event.listen(app.state.engine, "before_cursor_execute", capture)
        try:
            second = _post(client, token, "conté 22.50", "order-2", "conv-close")
        finally:
            event.remove(app.state.engine, "before_cursor_execute", capture)
    assert second.status_code == 200, second.text
    assert statements == ["update", "insert"], statements

    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 2
    previous, current = rows
    assert previous.superseded_by_id == current.id
    assert current.supersedes_cash_count_id == previous.id
    assert current.superseded_by_id is None
    assert len([row for row in rows if row.superseded_by_id is None]) == 1


def test_rollback_after_retiring_restores_the_previous_count(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    first = _post(client, token, "tengo 20 en caja", "rb-1", "conv-close")
    assert first.status_code == 200, first.text
    original = _counts(db_session, tenant.business_id)[0]
    original_counted_at = original.counted_at
    failed = _post(
        client,
        token,
        "conté 22.50",
        "rb-2",
        "conv-close",
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 1
    assert rows[0].id == original.id
    assert rows[0].amount == Decimal("20.00")
    assert rows[0].counted_at == original_counted_at
    assert rows[0].superseded_by_id is None
    audits = _rows(db_session, tenant.business_id, AuditEventRow, action="closing.submit_cash_count@1")
    events = _rows(db_session, tenant.business_id, OutboxEventRow, event_type="cash_count.recorded")
    assert len(audits) == 1
    assert len(events) == 1
    keys = {
        row.key: row.status
        for row in _rows(
            db_session,
            tenant.business_id,
            IdempotencyRecordRow,
            operation_type="lumo.message.record_cash_count",
        )
    }
    assert keys == {"rb-1": "completed"}
    retried = _post(client, token, "conté 22.50", "rb-2", "conv-close")
    assert retried.status_code == 200, retried.text
    assert _card(retried)["cash_status"] == "balanced"
    assert len(_counts(db_session, tenant.business_id)) == 2
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_no_compensating_supersede_write_exists() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "application" / "workflows" / "record_cash_count.py"
    ).read_text()
    assert "superseded_by_id" not in source


def test_committed_supersede_links_resolve_within_the_tenant(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    _post(client, token, "tengo 20 en caja", "link-1", "conv-close")
    _post(client, token, "conté 22.50", "link-2", "conv-close")
    _post(client, token, "tengo 30 en caja", "link-3", "conv-close")
    rows = _counts(db_session, tenant.business_id)
    by_id = {row.id: row for row in rows}
    assert len(rows) == 3
    for row in rows:
        for linked in (row.supersedes_cash_count_id, row.superseded_by_id):
            if linked is None:
                continue
            assert linked in by_id
            assert by_id[linked].business_id == row.business_id
    assert len([row for row in rows if row.superseded_by_id is None]) == 1
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_same_key_replay_and_conflict(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    first = _post(client, token, "tengo 20 en caja", "replay-1", "conv-close")
    replay = _post(client, token, "tengo 20 en caja", "replay-1", "conv-close")
    assert first.status_code == 200, first.text
    assert replay.status_code == 200, replay.text
    assert replay.json()["text"] == first.json()["text"]
    assert _card(replay) == _card(first)
    conflict = _post(client, token, "tengo 25 en caja", "replay-1", "conv-close")
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 1
    assert rows[0].amount == Decimal("20.00")
    assert len(_rows(db_session, tenant.business_id, OutboxEventRow, event_type="cash_count.recorded")) == 1


def test_replay_is_stale_and_new_key_read_back_is_live(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "800gr zanahoria")
    prepared = _post(client, token, "preparar el cierre", "stale-prep", "conv-close")
    assert _card(prepared)["expected_cash"]["amount"] == "20.00"
    counted = _post(client, token, "tengo 20 en caja", "stale-count", "conv-close")
    assert _card(counted)["cash_status"] == "balanced"
    _cash_sale(client, token, "extra", "100gr zanahoria")

    replay = _post(client, token, "tengo 20 en caja", "stale-count", "conv-close")
    replay_data = _card(replay)
    assert replay_data["expected_cash"]["amount"] == "20.00"
    assert replay_data["cash_difference"]["amount"] == "0.00"
    assert replay_data["cash_status"] == "balanced"

    live = _post(client, token, "tengo 20 en caja", "stale-live", "conv-close")
    live_data = _card(live)
    assert live_data["expected_cash"]["amount"] == "22.50"
    assert live_data["cash_difference"]["amount"] == "-2.50"
    assert live_data["cash_status"] == "short"
    assert live_data["cash_count_id"] == replay_data["cash_count_id"]
    assert live_data["counted_at"] == replay_data["counted_at"]

    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 1
    keys = [
        row.key
        for row in _rows(
            db_session,
            tenant.business_id,
            IdempotencyRecordRow,
            operation_type="lumo.message.record_cash_count",
        )
    ]
    assert keys == ["stale-count"]


def test_idempotency_matrix_row_deltas(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")

    def counters() -> tuple[int, int, int, int]:
        return (
            len(_counts(db_session, tenant.business_id)),
            len(_rows(db_session, tenant.business_id, AuditEventRow, action="closing.submit_cash_count@1")),
            len(_rows(db_session, tenant.business_id, OutboxEventRow, event_type="cash_count.recorded")),
            len(
                _rows(
                    db_session,
                    tenant.business_id,
                    IdempotencyRecordRow,
                    operation_type="lumo.message.record_cash_count",
                )
            ),
        )

    assert _post(client, token, "tengo 20 en caja", "mx-1", "conv-close").status_code == 200
    base = counters()
    assert base == (1, 1, 1, 1)

    assert _post(client, token, "tengo 20 en caja", "mx-1", "conv-close").status_code == 200
    assert counters() == base

    assert _post(client, token, "tengo 25 en caja", "mx-1", "conv-close").status_code == 409
    assert counters() == base

    assert _post(client, token, "tengo 20 en caja", "mx-2", "conv-close").status_code == 200
    assert counters() == base

    assert _post(client, token, "tengo 25 en caja", "mx-3", "conv-close").status_code == 200
    assert counters() == (2, 2, 2, 2)


def test_concurrent_recounts_keep_one_current_row(app, db_session) -> None:
    tenant, token = _seed(db_session)
    with TestClient(app, raise_server_exceptions=False) as setup:
        _cash_sale(setup, token, "cash", "900gr zanahoria")

    def count(utterance: str, key: str):
        with TestClient(app, raise_server_exceptions=False) as client:
            return _post(client, token, utterance, key, "conv-close")

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(count, "tengo 20 en caja", "race-1")
        right = pool.submit(count, "tengo 25 en caja", "race-2")
        first = left.result(timeout=30)
        second = right.result(timeout=30)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text

    rows = _counts(db_session, tenant.business_id)
    assert len(rows) == 2
    current = [row for row in rows if row.superseded_by_id is None]
    assert len(current) == 1
    superseded = [row for row in rows if row.superseded_by_id is not None]
    assert len(superseded) == 1
    assert superseded[0].superseded_by_id == current[0].id
    assert current[0].supersedes_cash_count_id == superseded[0].id
    assert {row.amount for row in rows} == {Decimal("20.00"), Decimal("25.00")}

    with TestClient(app, raise_server_exceptions=False) as client:
        readback = _post(
            client,
            token,
            f"tengo {current[0].amount:.2f} en caja".replace(".00", ""),
            "race-readback",
            "conv-close",
        )
    assert readback.status_code == 200, readback.text
    assert len(_counts(db_session, tenant.business_id)) == 2
    assert sale_integrity_orphans(db_session, tenant.business_id) == []


def test_rls_hides_and_blocks_other_business_counts(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    counted = _post(client, token, "tengo 20 en caja", "rls-count", "conv-close")
    assert counted.status_code == 200, counted.text
    carrota_count = _counts(db_session, tenant.business_id)[0]
    carrota_day_id = carrota_count.operational_day_id
    carrota_counted_at = carrota_count.counted_at

    other_id, other_user, other_token = seed_business(db_session, name="Other close")
    set_current_business_id(db_session, other_id)
    db_session.expire_all()
    assert db_session.scalars(select(CashCountRow)).all() == []

    prepared = _post(client, other_token, "preparar el cierre", "rls-prep", "conv-other")
    data = _card(prepared)
    assert data["operational_day_id"] is None
    assert data["expected_cash"]["amount"] == "0.00"
    assert data["cash_count_id"] is None
    blocked = _post(client, other_token, "tengo 20 en caja", "rls-write", "conv-other")
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["ui"] == []

    set_current_business_id(db_session, other_id)
    db_session.add(
        CashCountRow(
            business_id=other_id,
            operational_day_id=carrota_day_id,
            actor_id=other_user,
            amount=Decimal("20.00"),
            currency="MXN",
            source="manual_capture",
            counted_at=carrota_counted_at,
        )
    )
    # The day belongs to Carrota, so the write is refused by a day-scoped constraint and not by
    # RLS: either the current-count index or the composite day foreign key, whichever fires first.
    with pytest.raises(IntegrityError) as crossed:
        db_session.flush()
    assert any(
        name in str(crossed.value)
        for name in ("uq_cash_counts_current", "fk_cash_counts_operational_day")
    )
    db_session.rollback()
    db_session.expunge_all()
    assert len(_counts(db_session, tenant.business_id)) == 1


def test_unsupported_phrases_never_mutate(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    for index, phrase in enumerate(("tengo 1,200 en caja", "120", "cuánto falta en caja la semana pasada")):
        response = _post(client, token, phrase, f"unsupported-{index}", "conv-close")
        assert response.status_code == 200, response.text
        assert response.json()["ui"] == []
    assert _counts(db_session, tenant.business_id) == []
    assert _rows(db_session, tenant.business_id, AuditEventRow, action="closing.submit_cash_count@1") == []


def test_final_close_phrases_clarify_and_tools_stay_unregistered(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    counted = _post(client, token, "conté 22.50", "close-count", "conv-close")
    assert counted.status_code == 200, counted.text
    for index, phrase in enumerate(("cerrar el día", "confirmar cierre", "cerrar caja", "cerrar la jornada")):
        response = _post(client, token, phrase, f"close-{index}", "conv-close")
        assert response.status_code == 200, response.text
        assert response.json()["ui"] == []
        assert "no está disponible" in response.json()["text"]
    registry = ToolRegistry()
    register_conversational_sale_tools(registry)
    assert registry.get("closing.confirm@1") is None
    assert registry.get("closing.reopen@1") is None
    assert registry.get("closing.submit_cash_count@1") is SUBMIT_CASH_COUNT
    assert registry.get("closing.prepare@1") is CLOSING_PREPARE
    days = _rows(db_session, tenant.business_id, OperationalDayRow)
    assert [day.status for day in days] == ["open"]
    events = {
        row.event_type
        for row in _rows(db_session, tenant.business_id, OutboxEventRow)
    }
    assert not {event for event in events if "clos" in event and event != "cash_count.recorded"}
    assert len(_counts(db_session, tenant.business_id)) == 1
    absent = db_session.execute(
        text(
            """
            SELECT
                to_regclass('operations.closing_snapshots'),
                to_regclass('workflow.work_items'),
                to_regclass('workflow.outcome_runs'),
                to_regnamespace('workflow'),
                to_regnamespace('memory')
            """
        )
    ).one()
    assert all(item is None for item in absent)
    statuses = db_session.execute(
        text(
            """
            SELECT pg_get_constraintdef(oid) FROM pg_constraint
            WHERE conname = 'ck_operational_days_status'
            """
        )
    ).scalar_one()
    assert "'open'" in statuses and "closed" not in statuses


def test_tool_and_ui_registrations() -> None:
    assert SUBMIT_CASH_COUNT.permission == "closing.submit_cash_count"
    assert SUBMIT_CASH_COUNT.policy_id == "CLOSE-001"
    assert SUBMIT_CASH_COUNT.side_effect == "write"
    assert SUBMIT_CASH_COUNT.requires_idempotency is True
    assert list(SUBMIT_CASH_COUNT.input_schema["properties"]) == ["amount"]
    assert CLOSING_PREPARE.permission == "closing.submit_cash_count"
    assert CLOSING_PREPARE.policy_id == "CLOSE-002"
    assert CLOSING_PREPARE.side_effect == "read"
    assert CLOSING_PREPARE.requires_idempotency is False
    assert CLOSING_PREPARE.input_schema["properties"] == {}
    assert DAILY_CLOSE_PREPARATION_UI.component == "daily_close_preparation"
    assert DAILY_CLOSE_PREPARATION_UI.version == 1


def test_unregistered_close_cards_are_refused(app) -> None:
    from app.agent.generative_ui import GenerativeUIContract
    from app.domain.shared.errors import ValidationAppError

    composer = app.state.generative_ui_composer
    for component in ("closing_ready_card", "cash_difference_card"):
        with pytest.raises(ValidationAppError):
            composer.compose(
                GenerativeUIContract(
                    component=component,
                    version=1,
                    data={},
                    actions=[],
                    fallback_text="no",
                )
            )


def test_commit_attaches_the_day_and_counts_no_cash(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    days = _rows(db_session, tenant.business_id, OperationalDayRow)
    assert len(days) == 1
    assert days[0].status == "open"
    confirmed = [
        session
        for session in _rows(db_session, tenant.business_id, SaleSessionRow)
        if session.status == "confirmed"
    ]
    assert len(confirmed) == 1
    assert confirmed[0].operational_day_id == days[0].id
    assert _counts(db_session, tenant.business_id) == []
    set_current_business_id(db_session, tenant.business_id)
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(CashCountRow)
            .where(CashCountRow.business_id == tenant.business_id)
        )
        == 0
    )


def test_cash_count_does_not_touch_the_open_sale(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    added = _post(client, token, "500gr tomate", "open-add", "conv-open-sale")
    assert added.status_code == 200, added.text
    before_sessions = {
        session.id: (session.status, session.operational_day_id, session.updated_at)
        for session in _rows(db_session, tenant.business_id, SaleSessionRow)
    }
    before_payments = {payment.id: payment.amount for payment in _rows(db_session, tenant.business_id, PaymentRow)}
    before_items = len(_rows(db_session, tenant.business_id, SaleItemRow))
    before_day = _rows(db_session, tenant.business_id, OperationalDayRow)[0]
    before_day_state = (before_day.status, before_day.updated_at)

    counted = _post(client, token, "tengo 20 en caja", "open-count", "conv-open-sale")
    assert counted.status_code == 200, counted.text
    assert _card(counted)["cash_status"] == "short"

    after_sessions = {
        session.id: (session.status, session.operational_day_id, session.updated_at)
        for session in _rows(db_session, tenant.business_id, SaleSessionRow)
    }
    assert after_sessions == before_sessions
    assert {payment.id: payment.amount for payment in _rows(db_session, tenant.business_id, PaymentRow)} == (
        before_payments
    )
    assert len(_rows(db_session, tenant.business_id, SaleItemRow)) == before_items
    after_day = _rows(db_session, tenant.business_id, OperationalDayRow)[0]
    assert (after_day.status, after_day.updated_at) == before_day_state
    open_sessions = [
        session for session in _rows(db_session, tenant.business_id, SaleSessionRow) if session.status == "open"
    ]
    assert len(open_sessions) == 1
    assert open_sessions[0].operational_day_id is None
    assert len(_counts(db_session, tenant.business_id)) == 1


def test_preparation_read_after_a_count_writes_nothing(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "cash", "900gr zanahoria")
    counted = _post(client, token, "tengo 20 en caja", "read-count", "conv-close")
    assert counted.status_code == 200, counted.text

    def snapshot() -> tuple:
        return (
            [(row.id, row.amount, row.superseded_by_id) for row in _counts(db_session, tenant.business_id)],
            len(_rows(db_session, tenant.business_id, AuditEventRow)),
            len(_rows(db_session, tenant.business_id, OutboxEventRow)),
            len(_rows(db_session, tenant.business_id, IdempotencyRecordRow)),
            len(_rows(db_session, tenant.business_id, OperationalDayRow)),
        )

    before = snapshot()
    first = _post(client, token, "preparar el cierre", "read-1", "conv-close")
    second = _post(client, token, "cuánto debería haber en caja", "read-2", "conv-close")
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert _card(first) == _card(second)
    assert _card(first)["cash_status"] == "short"
    assert snapshot() == before


def test_repository_cash_methods_require_a_tenant(db_session) -> None:
    from app.domain.shared.errors import TenantScopeViolationError
    from app.domain.shared.tenant import TenantContext
    from app.infrastructure.persistence.operations import OperationsRepository

    repository = OperationsRepository(db_session)
    orphan = TenantContext(business_id=None, actor_id=None)  # type: ignore[arg-type]
    with pytest.raises(TenantScopeViolationError):
        repository.get_current_cash_count(tenant=orphan, operational_day_id=new_uuid7())
    with pytest.raises(TenantScopeViolationError):
        repository.expected_cash(tenant=orphan, operational_day_id=new_uuid7(), currency="MXN")
    with pytest.raises(TenantScopeViolationError):
        repository.lock_day_for_update(tenant=orphan, business_date=date(2026, 9, 21))
