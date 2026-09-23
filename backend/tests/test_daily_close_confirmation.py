from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.application.closing_confirmation_token import issue_closing_confirmation_token
from app.domain.operations.cash_count import CashStatus
from app.domain.operations.closing_snapshot import preparation_fingerprint, status_for_difference
from app.infrastructure.persistence.models import (
    AuditEventRow,
    ClosingSnapshotRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutboxEventRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import ensure_carrota_seed
from app.policies import PolicyRequest
from app.policies.engine import CLOSE_003, SEC_002, FoundationPolicyEngine
from tests.conftest import seed_business
from tests.sale_cleanup import clear_tenant_sale_mutations, sale_integrity_orphans
from tests.test_daily_close_preparation import _cash_sale, _rows

BUSINESS = UUID("01900000-0000-7000-8000-000000000001")
DAY = UUID("01900000-0000-7000-8000-000000000010")
COUNT = UUID("01900000-0000-7000-8000-000000000011")


def _auth(token: str, **extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", **extra}


def _post(
    client: TestClient,
    token: str,
    message: str,
    key: str,
    conversation_id: str,
    *,
    client_context: dict | None = None,
    **extra: str,
):
    body: dict = {"message": message, "conversation_id": conversation_id}
    if client_context is not None:
        body["client_context"] = client_context
    return client.post(
        "/api/v1/lumo/messages",
        json=body,
        headers=_auth(token, **{"Idempotency-Key": key, **extra}),
    )


def _seed(db_session):
    tenant, token = ensure_carrota_seed(db_session, token_secret="test-dev-secret-16-chars-minimum")
    db_session.commit()
    clear_tenant_sale_mutations(db_session, tenant.business_id)
    return tenant, token


def _token_of(response) -> str | None:
    ui = response.json()["ui"]
    if not ui:
        return None
    value = ui[0]["data"].get("confirmation_token")
    return value if isinstance(value, str) and value else None


def _ready(client, token, prefix: str, counted: str = "22.50"):
    _cash_sale(client, token, prefix, "900gr zanahoria")
    counted_response = _post(client, token, f"conté {counted}", f"{prefix}-count", f"conv-{prefix}")
    assert counted_response.status_code == 200, counted_response.text
    requested = _post(client, token, "cerrar el día", f"{prefix}-req", f"conv-{prefix}")
    assert requested.status_code == 200, requested.text
    confirmation = _token_of(requested)
    assert confirmation
    assert confirmation not in requested.json()["text"]
    return confirmation, requested


def _confirm(client, token, prefix: str, confirmation: str, *, key: str | None = None, message: str = "confirmar cierre", **extra):
    return _post(
        client,
        token,
        message,
        key or f"{prefix}-confirm",
        f"conv-{prefix}",
        client_context={"confirmation_token": confirmation},
        **extra,
    )


def _day(db_session, business_id) -> OperationalDayRow:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return db_session.scalars(select(OperationalDayRow).where(OperationalDayRow.business_id == business_id)).one()


def _snapshots(db_session, business_id) -> list[ClosingSnapshotRow]:
    return _rows(db_session, business_id, ClosingSnapshotRow)


def test_preparation_fingerprint_is_v1_sha256() -> None:
    digest = preparation_fingerprint(
        business_id=BUSINESS,
        operational_day_id=DAY,
        cash_count_id=COUNT,
        business_date=datetime(2026, 9, 22, tzinfo=UTC).date(),
        currency="MXN",
        sale_count=1,
        gross_sales_total="22.50",
        cash_total=Decimal("22.5"),
        card_total="0",
        transfer_total="0.00",
        expected_cash="22.50",
        counted_cash="20.00",
        cash_difference="-2.50",
        cash_status="short",
    )
    canonical = (
        f"v1|{BUSINESS}|{DAY}|{COUNT}|2026-09-22|MXN|1|22.50|22.50|0.00|0.00|22.50|20.00|-2.50|short"
    )
    assert digest == sha256(canonical.encode()).hexdigest()
    changed = preparation_fingerprint(
        business_id=BUSINESS,
        operational_day_id=DAY,
        cash_count_id=COUNT,
        business_date=datetime(2026, 9, 22, tzinfo=UTC).date(),
        currency="MXN",
        sale_count=1,
        gross_sales_total="22.50",
        cash_total="22.50",
        card_total="0.00",
        transfer_total="0.00",
        expected_cash="22.50",
        counted_cash="22.50",
        cash_difference="0.00",
        cash_status="balanced",
    )
    assert changed != digest
    assert status_for_difference(Decimal("-2.50")) is CashStatus.SHORT
    assert status_for_difference(Decimal("2.50")) is CashStatus.OVER
    assert status_for_difference(Decimal("0")) is CashStatus.BALANCED
    with pytest.raises(TypeError, match="must not use float"):
        preparation_fingerprint(
            business_id=BUSINESS,
            operational_day_id=DAY,
            cash_count_id=COUNT,
            business_date=datetime(2026, 9, 22, tzinfo=UTC).date(),
            currency="MXN",
            sale_count=1,
            gross_sales_total=22.50,
            cash_total="22.50",
            card_total="0.00",
            transfer_total="0.00",
            expected_cash="22.50",
            counted_cash="22.50",
            cash_difference="0.00",
            cash_status="balanced",
        )


def test_close_003_allows_token_and_denies_server_owned_amounts() -> None:
    engine = FoundationPolicyEngine()
    allowed = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.confirm@1",
            tool_registered=True,
            from_llm=True,
            arguments={"confirmation_token": "signed"},
        )
    )
    assert allowed.decision.value == "allow"
    assert CLOSE_003 in allowed.rule_ids
    denied = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.confirm@1",
            tool_registered=True,
            from_llm=True,
            arguments={"confirmation_token": "signed", "counted_cash": "22.50"},
        )
    )
    assert denied.decision.value == "deny"
    assert CLOSE_003 in denied.rule_ids
    reopen = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.reopen@1",
            tool_registered=False,
            from_llm=True,
            arguments={},
        )
    )
    assert reopen.decision.value == "deny"
    assert SEC_002 in reopen.rule_ids


def test_request_close_without_a_day_or_count_does_not_confirm(client, db_session) -> None:
    tenant, token = _seed(db_session)
    missing_day = _post(client, token, "cerrar el día", "no-day", "conv-no-day")
    assert missing_day.status_code == 200, missing_day.text
    assert missing_day.json()["text"] == "No hay una jornada abierta para cerrar hoy."
    assert _token_of(missing_day) is None

    _cash_sale(client, token, "nocount", "900gr zanahoria")
    missing_count = _post(client, token, "cerrar caja", "no-count", "conv-nocount")
    assert missing_count.status_code == 200, missing_count.text
    assert missing_count.json()["text"] == "Falta contar el efectivo antes de cerrar."
    assert _token_of(missing_count) is None
    assert _day(db_session, tenant.business_id).status == "open"
    assert _snapshots(db_session, tenant.business_id) == []


def test_balanced_short_and_over_close_only_after_confirmation(client, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, requested = _ready(client, token, "bal", "22.50")
    assert "1 venta" in requested.json()["text"]
    assert "¿Confirmas el cierre?" in requested.json()["text"]
    assert _day(db_session, tenant.business_id).status == "open"
    assert _snapshots(db_session, tenant.business_id) == []

    closed = _confirm(client, token, "bal", confirmation)
    assert closed.status_code == 200, closed.text
    body = closed.json()
    assert body["ui"][0]["component"] == "daily_close_confirmed"
    assert body["ui"][0]["version"] == 1
    assert body["ui"][0]["actions"] == []
    assert body["ui"][0]["data"]["cash_status"] == "balanced"
    assert body["text"].startswith("Cierre confirmado")
    assert "Caja cuadrada" in body["text"]
    assert "confirmation_token" not in body["ui"][0]["data"]
    assert confirmation not in body["text"]
    snapshot = _snapshots(db_session, tenant.business_id)[0]
    assert snapshot.cash_status == "balanced"
    assert snapshot.cash_difference == Decimal("0.00")
    assert _day(db_session, tenant.business_id).status == "closed"
    assert sale_integrity_orphans(db_session, tenant.business_id) == []

    _seed(db_session)
    short_token, _short_requested = _ready(client, token, "short", "20.00")
    short = _confirm(client, token, "short", short_token)
    assert short.status_code == 200, short.text
    assert short.json()["ui"][0]["data"]["cash_status"] == "short"
    assert "Faltante" in short.json()["text"]
    assert _snapshots(db_session, tenant.business_id)[0].cash_difference == Decimal("-2.50")

    _seed(db_session)
    over_token, _over_requested = _ready(client, token, "over", "25.00")
    over = _confirm(client, token, "over", over_token)
    assert over.status_code == 200, over.text
    assert over.json()["ui"][0]["data"]["cash_status"] == "over"
    assert "Sobrante" in over.json()["text"]
    assert _snapshots(db_session, tenant.business_id)[0].cash_difference == Decimal("2.50")


def test_missing_invalid_and_stale_confirmation_do_not_close(client, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "guard")
    missing = _post(client, token, "confirmar cierre", "guard-missing", "conv-guard")
    assert missing.status_code == 200, missing.text
    assert missing.json()["text"] == "Para cerrar, confirma el resumen del cierre."
    assert missing.json()["ui"] == []

    invalid = _confirm(client, token, "guard", "not-a-token", key="guard-invalid")
    assert invalid.status_code == 200, invalid.text
    assert invalid.json()["text"] == "Esa confirmación no es válida. Pide el cierre otra vez."
    assert _day(db_session, tenant.business_id).status == "open"

    issued = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)
    fresh, _requested_at = _ready_at(client, token, "exp", issued)
    expired = _confirm(
        client,
        token,
        "exp",
        fresh,
        key="exp-late",
        **{"X-Debug-Now": (issued + timedelta(minutes=16)).isoformat()},
    )
    assert expired.status_code == 200, expired.text
    assert expired.json()["text"] == "Esa confirmación no es válida. Pide el cierre otra vez."

    stale_token, _stale_requested = _ready(client, token, "stale")
    recounted = _post(client, token, "conté 20", "stale-recount", "conv-stale")
    assert recounted.status_code == 200, recounted.text
    stale = _confirm(client, token, "stale", stale_token, key="stale-confirm")
    assert stale.status_code == 200, stale.text
    assert stale.json()["text"] == "El cierre cambió. Revisa los datos y confírmalo otra vez."
    refreshed = _token_of(stale)
    assert refreshed and refreshed != stale_token
    assert refreshed not in stale.json()["text"]
    set_current_business_id(db_session, tenant.business_id)
    days = db_session.scalars(
        select(OperationalDayRow).where(OperationalDayRow.business_id == tenant.business_id)
    ).all()
    assert days
    assert all(day.status == "open" for day in days)
    assert _snapshots(db_session, tenant.business_id) == []
    assert _rows(db_session, tenant.business_id, IdempotencyRecordRow, operation_type="lumo.message.confirm_close") == []


def _ready_at(client, token, prefix: str, now: datetime):
    header = {"X-Debug-Now": now.isoformat()}
    added = _post(client, token, "900gr zanahoria", f"{prefix}-add", f"conv-{prefix}", **header)
    assert added.status_code == 200, added.text
    totaled = _post(client, token, "totalizar", f"{prefix}-tot", f"conv-{prefix}", **header)
    assert totaled.status_code == 200, totaled.text
    paid = _post(client, token, "efectivo", f"{prefix}-pay", f"conv-{prefix}", **header)
    assert paid.status_code == 200, paid.text
    counted = _post(client, token, "conté 22.50", f"{prefix}-count", f"conv-{prefix}", **header)
    assert counted.status_code == 200, counted.text
    requested = _post(client, token, "cerrar el día", f"{prefix}-req", f"conv-{prefix}", **header)
    assert requested.status_code == 200, requested.text
    confirmation = _token_of(requested)
    assert confirmation
    return confirmation, requested


def test_idempotent_replay_and_different_key_read_back(client, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "idem")
    first = _confirm(client, token, "idem", confirmation, key="idem-1")
    assert first.status_code == 200, first.text
    replay = _confirm(client, token, "idem", confirmation, key="idem-1")
    assert replay.status_code == 200, replay.text
    assert replay.json()["text"] == first.json()["text"]
    conflict = _confirm(client, token, "idem", confirmation, key="idem-1", message="si, cerrar")
    assert conflict.status_code == 409
    other = _confirm(client, token, "idem", confirmation, key="idem-2", message="confirmar")
    assert other.status_code == 200, other.text
    assert other.json()["ui"][0]["component"] == "daily_close_confirmed"
    assert len(_snapshots(db_session, tenant.business_id)) == 1
    assert len(_rows(db_session, tenant.business_id, AuditEventRow, action="closing.confirm@1")) == 1
    assert len(_rows(db_session, tenant.business_id, OutboxEventRow, event_type="closing.confirmed")) == 1
    assert (
        len(_rows(db_session, tenant.business_id, IdempotencyRecordRow, operation_type="lumo.message.confirm_close"))
        == 1
    )
    audit = _rows(db_session, tenant.business_id, AuditEventRow, action="closing.confirm@1")[0]
    assert audit.before_payload["status"] == "open"
    assert audit.after_payload["previous_status"] == "open"
    assert audit.after_payload["new_status"] == "closed"
    assert audit.after_payload["closing_snapshot_id"]


def test_failed_confirm_rolls_back_and_can_be_retried(client, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "roll")
    failed = _confirm(client, token, "roll", confirmation, key="roll-1", **{"X-Debug-Fail-After-Write": "1"})
    assert failed.status_code >= 500
    assert _day(db_session, tenant.business_id).status == "open"
    assert _snapshots(db_session, tenant.business_id) == []
    assert _rows(db_session, tenant.business_id, OutboxEventRow, event_type="closing.confirmed") == []
    closed = _confirm(client, token, "roll", confirmation, key="roll-2")
    assert closed.status_code == 200, closed.text
    assert _day(db_session, tenant.business_id).status == "closed"


def test_closed_day_refuses_sale_and_recount_and_serves_frozen_reads(client, db_session) -> None:
    tenant, token = _seed(db_session)
    _post(client, token, "900gr zanahoria", "open-add", "conv-open-sale")
    confirmation, _requested = _ready(client, token, "done")
    closed = _confirm(client, token, "done", confirmation)
    assert closed.status_code == 200, closed.text
    snapshot = _snapshots(db_session, tenant.business_id)[0]

    assert _post(client, token, "900gr zanahoria", "done-sale-add", "conv-done-sale").status_code == 200
    assert _post(client, token, "totalizar", "done-sale-tot", "conv-done-sale").status_code == 200
    sale = _post(client, token, "efectivo", "done-sale-pay", "conv-done-sale")
    assert sale.status_code == 200, sale.text
    assert sale.json()["text"] == "La jornada de hoy ya está cerrada. No puedo registrar otra venta en ese día."
    recount = _post(client, token, "conté 30", "done-recount", "conv-done")
    assert recount.status_code == 200, recount.text
    assert recount.json()["text"] == "La jornada de hoy ya está cerrada. No puedo cambiar el conteo."

    prepared = _post(client, token, "preparar el cierre", "done-prep", "conv-done")
    assert prepared.json()["ui"][0]["component"] == "daily_close_confirmed"
    assert prepared.json()["ui"][0]["data"]["sale_count"] == snapshot.sale_count
    assert prepared.json()["ui"][0]["data"]["gross_sales_total"]["amount"] == f"{snapshot.gross_sales_total:.2f}"
    assert _token_of(prepared) is None

    summary = _post(client, token, "como vamos hoy", "done-sum", "conv-done")
    assert summary.json()["ui"][0]["component"] == "operational_day_summary"
    assert summary.json()["ui"][0]["data"]["status"] == "closed"
    assert summary.json()["ui"][0]["data"]["sale_count"] == 1

    nxt = _post(
        client,
        token,
        "900gr zanahoria",
        "next-add",
        "conv-next",
        **{"X-Debug-Now": "2026-09-23T18:00:00+00:00"},
    )
    assert nxt.status_code == 200, nxt.text
    assert "ya está cerrada" not in nxt.json()["text"]
    assert len(_snapshots(db_session, tenant.business_id)) == 1


def test_in_progress_session_does_not_block_close(client, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "prog")
    started = _post(client, token, "900gr zanahoria", "prog-open", "conv-prog-open")
    assert started.status_code == 200, started.text
    closed = _confirm(client, token, "prog", confirmation)
    assert closed.status_code == 200, closed.text
    assert closed.json()["ui"][0]["data"]["sale_count"] == 1
    assert _day(db_session, tenant.business_id).status == "closed"


def test_concurrent_confirms_create_one_close(client, db_session, app) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "race")

    def confirm(key: str):
        with TestClient(app) as local:
            return _confirm(local, token, "race", confirmation, key=key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        left = pool.submit(confirm, "race-a")
        right = pool.submit(confirm, "race-b")
        first = left.result(timeout=30)
        second = right.result(timeout=30)
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["ui"][0]["component"] == "daily_close_confirmed"
    assert second.json()["ui"][0]["component"] == "daily_close_confirmed"
    assert len(_snapshots(db_session, tenant.business_id)) == 1
    assert len(_rows(db_session, tenant.business_id, OutboxEventRow, event_type="closing.confirmed")) == 1
    assert len(_rows(db_session, tenant.business_id, AuditEventRow, action="closing.confirm@1")) == 1


def test_confirm_races_recount_and_sale_without_a_partial_close(client, db_session, app) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "mix")

    def confirm():
        with TestClient(app) as local:
            return _confirm(local, token, "mix", confirmation, key="mix-confirm")

    def recount():
        with TestClient(app) as local:
            return _post(local, token, "conté 20", "mix-recount", "conv-mix")

    with ThreadPoolExecutor(max_workers=2) as pool:
        confirmed = pool.submit(confirm)
        recounted = pool.submit(recount)
        confirm_response = confirmed.result(timeout=30)
        recount_response = recounted.result(timeout=30)
    assert confirm_response.status_code == 200, confirm_response.text
    assert recount_response.status_code == 200, recount_response.text
    day = _day(db_session, tenant.business_id)
    snapshots = _snapshots(db_session, tenant.business_id)
    if day.status == "closed":
        assert len(snapshots) == 1
        assert recount_response.json()["text"] == "La jornada de hoy ya está cerrada. No puedo cambiar el conteo."
    else:
        assert snapshots == []
        assert confirm_response.json()["text"] == "El cierre cambió. Revisa los datos y confírmalo otra vez."

    _seed(db_session)
    sale_token, _requested_sale = _ready(client, token, "sale-race")
    assert _post(client, token, "900gr zanahoria", "sale-race-add-2", "conv-sale-race-2").status_code == 200
    assert _post(client, token, "totalizar", "sale-race-tot-2", "conv-sale-race-2").status_code == 200

    def confirm_sale():
        with TestClient(app) as local:
            return _confirm(local, token, "sale-race", sale_token, key="sale-race-confirm")

    def pay_sale():
        with TestClient(app) as local:
            return _post(local, token, "efectivo", "sale-race-pay-2", "conv-sale-race-2")

    with ThreadPoolExecutor(max_workers=2) as pool:
        confirmed = pool.submit(confirm_sale)
        sold = pool.submit(pay_sale)
        confirm_response = confirmed.result(timeout=30)
        sale_response = sold.result(timeout=30)
    assert confirm_response.status_code == 200, confirm_response.text
    assert sale_response.status_code == 200, sale_response.text
    day = _day(db_session, tenant.business_id)
    snapshots = _snapshots(db_session, tenant.business_id)
    if sale_response.json()["text"] == "La jornada de hoy ya está cerrada. No puedo registrar otra venta en ese día.":
        assert day.status == "closed"
        assert len(snapshots) == 1
        assert snapshots[0].sale_count == 1
    else:
        assert confirm_response.json()["text"] == "El cierre cambió. Revisa los datos y confírmalo otra vez."
        assert day.status == "open"
        assert snapshots == []


def test_wrong_actor_token_is_invalid(client, db_session) -> None:
    _tenant, token = _seed(db_session)
    confirmation, requested = _ready(client, token, "actor")
    data = requested.json()["ui"][0]["data"]
    forged = issue_closing_confirmation_token(
        secret="test-dev-secret-16-chars-minimum",
        business_id=BUSINESS,
        actor_id=UUID("01900000-0000-7000-8000-000000000099"),
        operational_day_id=UUID(data["operational_day_id"]),
        cash_count_id=UUID(data["cash_count_id"]),
        fingerprint="not-the-live-fingerprint",
        issued_at=datetime.now(UTC),
    )
    assert forged != confirmation
    rejected = _confirm(client, token, "actor", forged, key="actor-confirm")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["text"] == "Esa confirmación no es válida. Pide el cierre otra vez."


def test_other_business_cannot_read_a_closing_snapshot(client, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, _requested = _ready(client, token, "rls")
    closed = _confirm(client, token, "rls", confirmation)
    assert closed.status_code == 200, closed.text
    other_id, _other_user, other_token = seed_business(db_session, name="Other close reader")
    set_current_business_id(db_session, other_id)
    db_session.expire_all()
    assert db_session.scalars(select(ClosingSnapshotRow)).all() == []
    prepared = _post(client, other_token, "preparar el cierre", "rls-prep", "conv-rls-other")
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["ui"][0]["component"] == "daily_close_preparation"
    assert prepared.json()["ui"][0]["data"]["cash_count_id"] is None
    assert _snapshots(db_session, tenant.business_id)
