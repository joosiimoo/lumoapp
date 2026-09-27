"""Business Stream read model. Test-owned tenants only."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm.attributes import flag_modified

from app.application.queries.get_business_stream import GetBusinessStream
from app.application.workflows.get_daily_close_preparation import business_date_now
from app.domain.operations.business_stream import OperatorState, select_business_stream_state
from app.domain.operations.day import OperationalDay, OperationalDayStatus
from app.domain.operations.work_item import WorkItemType
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import (
    AuditEventRow,
    BusinessEventRow,
    CashCountRow,
    ClosingSnapshotRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutcomeRunRow,
    OutboxEventRow,
    SourceCoverageRecordRow,
    WorkItemRow,
)
from app.infrastructure.persistence.rls import set_current_business_id
from app.infrastructure.persistence.seed import CARROTA_BUSINESS_ID
from tests.isolation import seed_catalog_tenant
from tests.test_daily_close_confirmation import _confirm, _ready

_TRACKED = (
    OperationalDayRow,
    WorkItemRow,
    OutcomeRunRow,
    CashCountRow,
    ClosingSnapshotRow,
    SourceCoverageRecordRow,
    BusinessEventRow,
    AuditEventRow,
    OutboxEventRow,
    IdempotencyRecordRow,
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get(client: TestClient, token: str, **params: str):
    return client.get("/api/v1/business-stream/today", params=params, headers=_auth(token))


def _count(db_session, business_id: UUID, model) -> int:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    value = db_session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id))
    return int(value or 0)


def _counts(db_session, business_id: UUID) -> dict[str, int]:
    return {model.__tablename__: _count(db_session, business_id, model) for model in _TRACKED}


def test_selector_closed_states() -> None:
    idle, idle_progress = select_business_stream_state(day_status=None, desired_type=None, has_snapshot=False)
    assert idle is OperatorState.NO_ACTIVE_DAY
    assert idle_progress.value == "none"
    organizing, progressing = select_business_stream_state(
        day_status=OperationalDayStatus.OPEN,
        desired_type=None,
        has_snapshot=False,
    )
    assert organizing is OperatorState.ORGANIZING
    assert progressing.value == "progressing"
    unavailable, missing_progress = select_business_stream_state(
        day_status=OperationalDayStatus.CLOSED,
        desired_type=None,
        has_snapshot=False,
    )
    assert unavailable is OperatorState.UNAVAILABLE
    assert missing_progress is None


def test_missing_snapshot_is_unavailable_without_summary() -> None:
    class _Business:
        timezone = "America/Mexico_City"

    class _Identities:
        def get_business(self, tenant: TenantContext):
            return _Business()

    class _Operations:
        def __init__(self) -> None:
            self.summarized = 0

        def get_by_date(self, *, tenant: TenantContext, business_date):
            return OperationalDay(
                id=new_uuid7(),
                business_id=tenant.business_id,
                business_date=business_date,
                status=OperationalDayStatus.CLOSED,
                timezone="America/Mexico_City",
            )

        def get_snapshot_for_day(self, *, tenant: TenantContext, operational_day_id: UUID):
            return None

        def summarize_day(self, **kwargs):
            self.summarized += 1
            raise AssertionError("closed day without a snapshot must not use the summary")

    operations = _Operations()
    tenant = TenantContext(business_id=new_uuid7(), actor_id=new_uuid7())
    body = GetBusinessStream(_Identities(), operations).execute(tenant=tenant)
    assert operations.summarized == 0
    assert body["operator_state"] == "unavailable"
    assert body["close_progress"] is None
    assert body["responsibility"] == "No pude consultar el estado de hoy."
    assert body["factual_summary"] is None
    assert body["attention"] is None
    assert body["primary_action"] is None
    assert body["coverage"] is None


def test_no_active_day_has_no_facts_and_writes_nothing(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    assert tenant.business_id != CARROTA_BUSINESS_ID
    before = _counts(db_session, tenant.business_id)
    response = _get(client, token)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "business_date",
        "operator_state",
        "close_progress",
        "responsibility",
        "detail",
        "factual_summary",
        "attention",
        "primary_action",
        "coverage",
        "as_of",
    }
    assert body["operator_state"] == "no_active_day"
    assert body["close_progress"] == "none"
    assert body["responsibility"] == "Cuando empiece la actividad, organizo el día."
    assert body["detail"] is None
    assert body["factual_summary"] is None
    assert body["attention"] is None
    assert body["primary_action"] is None
    assert body["coverage"] is None
    assert body["as_of"]
    assert _counts(db_session, tenant.business_id) == before
    assert _count(db_session, tenant.business_id, OperationalDayRow) == 0


def test_open_day_without_desired_type_is_organizing(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    _, business_date = business_date_now(timezone_name="America/Mexico_City", now=None)
    set_current_business_id(db_session, tenant.business_id)
    db_session.add(
        OperationalDayRow(
            id=new_uuid7(),
            business_id=tenant.business_id,
            business_date=business_date,
            status="open",
            timezone="America/Mexico_City",
        )
    )
    db_session.commit()
    body = _get(client, token).json()
    assert body["operator_state"] == "organizing"
    assert body["close_progress"] == "progressing"
    assert body["responsibility"] == "Lumo está organizando el cierre"
    assert body["detail"] == "Con lo registrado hasta ahora."
    assert body["primary_action"] is None
    assert body["attention"] is None
    assert body["factual_summary"]["basis"] == "registered_sales"
    assert body["factual_summary"]["sale_count"] == 0
    assert body["coverage"]["sentence"] == "Este cierre considera las operaciones registradas en Lumo."
    assert body["coverage"]["limitation_code"] == "only_lumo_registered_operations"


def test_cash_count_short_over_ready_and_closed(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    confirmation, _requested = _ready(client, token, "stream-ready", "22.50")
    ready = _get(client, token)
    assert ready.status_code == 200, ready.text
    ready_body = ready.json()
    assert ready_body["operator_state"] == "ready_to_close"
    assert ready_body["close_progress"] == "ready"
    assert ready_body["responsibility"] == "Cierre listo para confirmar"
    assert ready_body["primary_action"]["label"] == "Revisar cierre"
    assert ready_body["primary_action"]["message"] == "cerrar el día"
    assert ready_body["primary_action"]["action_id"] is None
    assert ready_body["primary_action"]["kind"] == "request_close"
    assert "closing.request@1" not in ready.text
    assert "Confirmar cierre" not in ready.text
    assert "context_token" not in ready.text
    assert ready_body["factual_summary"]["cash_status"] == "balanced"
    assert ready_body["factual_summary"]["expected_cash"]["amount"] == "22.50"

    confirmed = _confirm(client, token, "stream-ready", confirmation)
    assert confirmed.status_code == 200, confirmed.text
    closed = _get(client, token).json()
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    snapshot = db_session.scalars(
        select(ClosingSnapshotRow).where(ClosingSnapshotRow.business_id == tenant.business_id)
    ).one()
    summary = closed["factual_summary"]
    assert closed["operator_state"] == "closed"
    assert closed["close_progress"] == "completed"
    assert closed["responsibility"] == "Cierre completado"
    assert closed["primary_action"] is None
    assert summary["basis"] == "closing_snapshot"
    assert summary["sale_count"] == snapshot.sale_count
    assert summary["gross_sales_total"]["amount"] == f"{snapshot.gross_sales_total:.2f}"
    assert summary["cash_total"]["amount"] == f"{snapshot.cash_total:.2f}"
    assert summary["expected_cash"]["amount"] == f"{snapshot.expected_cash:.2f}"
    assert summary["counted_cash"]["amount"] == f"{snapshot.counted_cash:.2f}"
    assert summary["cash_difference"]["amount"] == f"{snapshot.cash_difference:.2f}"
    assert summary["cash_status"] == snapshot.cash_status
    assert summary["closed_at"]
    assert closed["coverage"]["limitation_code"] == "only_lumo_registered_operations"

    counted, counted_token = seed_catalog_tenant(db_session)
    from tests.test_daily_close_preparation import _cash_sale, _post

    _cash_sale(client, counted_token, "stream-count", "900gr zanahoria")
    waiting = _get(client, counted_token).json()
    assert waiting["operator_state"] == "cash_count_required"
    assert waiting["close_progress"] == "waiting"
    assert waiting["responsibility"] == "Necesito que registres el efectivo contado"
    assert "$22.50" in waiting["detail"]
    assert waiting["factual_summary"]["expected_cash"] == {"amount": "22.50", "currency": "MXN"}
    assert waiting["factual_summary"]["counted_cash"] is None
    assert waiting["factual_summary"]["cash_difference"] is None
    assert waiting["factual_summary"]["cash_status"] == "not_counted"
    assert waiting["factual_summary"]["basis"] == "registered_sales"
    assert waiting["attention"]["why"] == "Hace falta para continuar con el cierre."
    action = waiting["primary_action"]
    assert action["kind"] == "record_cash_count"
    assert action["label"] == "Registrar conteo"
    assert action["invocation"] == "composer"
    assert action["message"] is None
    assert action["action_id"] is None
    assert action["work_item_id"]
    assert action["outcome_run_id"]
    assert "work_item_id" not in set(waiting)

    short_tenant, short_token = seed_catalog_tenant(db_session)
    _cash_sale(client, short_token, "stream-short", "900gr zanahoria")
    short_count = _post(client, short_token, "conté 20.00", "stream-short-count", "conv-stream-short")
    assert short_count.status_code == 200, short_count.text
    short = _get(client, short_token).json()
    assert short["operator_state"] == "cash_difference"
    assert short["responsibility"] == "Esperando tu revisión"
    assert short["detail"] is None
    assert short["attention"]["why"] == "La diferencia queda visible. No indica por qué ocurrió."
    assert short["factual_summary"]["expected_cash"]["amount"] == "22.50"
    assert short["factual_summary"]["counted_cash"]["amount"] == "20.00"
    assert short["factual_summary"]["cash_difference"]["amount"] == "-2.50"
    assert short["factual_summary"]["cash_status"] == "short"
    assert short["primary_action"]["label"] == "Revisar cierre"
    assert short["primary_action"]["message"] == "cerrar el día"
    assert short["primary_action"]["action_id"] is None
    assert "recount" not in json.dumps(short).casefold()
    assert counted.business_id != short_tenant.business_id


def test_over_uses_server_difference(client: TestClient, db_session) -> None:
    _tenant, token = seed_catalog_tenant(db_session)
    from tests.test_daily_close_preparation import _cash_sale, _post

    _cash_sale(client, token, "stream-over", "900gr zanahoria")
    counted = _post(client, token, "conté 25.00", "stream-over-count", "conv-stream-over")
    assert counted.status_code == 200, counted.text
    body = _get(client, token).json()
    assert body["operator_state"] == "cash_difference"
    assert body["factual_summary"]["cash_status"] == "over"
    assert body["factual_summary"]["cash_difference"]["amount"] == "2.50"
    assert body["primary_action"]["label"] == "Revisar cierre"
    assert body["primary_action"]["action_id"] is None


def test_repeated_get_writes_nothing(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    from tests.test_daily_close_preparation import _cash_sale

    _cash_sale(client, token, "stream-repeat", "900gr zanahoria")
    before = _counts(db_session, tenant.business_id)
    first = _get(client, token)
    second = _get(client, token)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["operator_state"] == second.json()["operator_state"] == "cash_count_required"
    assert _counts(db_session, tenant.business_id) == before


def test_unknown_query_and_missing_routes(client: TestClient, db_session) -> None:
    _tenant, token = seed_catalog_tenant(db_session)
    rejected = _get(client, token, date="2026-09-26")
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get("/api/v1/operational-days/current/outcome", headers=_auth(token)).status_code == 404
    assert client.get("/api/v1/operational-days/current/work-items", headers=_auth(token)).status_code == 404
    assert client.get("/api/v1/source-coverage", headers=_auth(token)).status_code == 404
    assert client.get("/api/v1/business-stream/today", headers=_auth(token)).status_code == 200


def test_tenant_cannot_read_another_stream(client: TestClient, db_session) -> None:
    owner, owner_token = seed_catalog_tenant(db_session)
    other, other_token = seed_catalog_tenant(db_session)
    from tests.test_daily_close_preparation import _cash_sale

    _cash_sale(client, owner_token, "stream-owner", "900gr zanahoria")
    owner_body = _get(client, owner_token).json()
    foreign = _get(client, other_token)
    assert foreign.status_code == 200, foreign.text
    assert foreign.json()["operator_state"] == "no_active_day"
    assert "22.50" not in foreign.text
    assert owner_body["primary_action"]["work_item_id"] not in foreign.text
    assert owner.business_id != other.business_id
    assert str(owner.business_id) not in foreign.text


def test_stale_outcome_does_not_override_live_cash(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    from tests.test_daily_close_preparation import _cash_sale, _post

    _cash_sale(client, token, "stream-stale", "900gr zanahoria")
    counted = _post(client, token, "conté 22.50", "stream-stale-count", "conv-stream-stale")
    assert counted.status_code == 200, counted.text
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    run = db_session.scalars(select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id)).one()
    evidence = dict(run.evidence)
    evidence.pop("current_cash_count_id", None)
    evidence["cash_status"] = "not_counted"
    run.status = "in_progress"
    run.reason_code = "awaiting_cash_count"
    run.ready_at = None
    run.evidence = evidence
    flag_modified(run, "evidence")
    db_session.commit()
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    stored = db_session.scalars(select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id)).one()
    status_before = stored.status
    reason_before = stored.reason_code
    updated_before = stored.updated_at
    body = _get(client, token).json()
    assert body["operator_state"] == "ready_to_close"
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    after = db_session.scalars(select(OutcomeRunRow).where(OutcomeRunRow.business_id == tenant.business_id)).one()
    assert after.status == status_before == "in_progress"
    assert after.reason_code == reason_before
    assert after.updated_at == updated_before


def test_missing_work_item_is_not_inserted(client: TestClient, db_session) -> None:
    tenant, token = seed_catalog_tenant(db_session)
    from tests.test_daily_close_preparation import _cash_sale

    _cash_sale(client, token, "stream-missing-item", "900gr zanahoria")
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    item = db_session.scalars(
        select(WorkItemRow).where(WorkItemRow.business_id == tenant.business_id, WorkItemRow.status == "open")
    ).one()
    assert item.type == WorkItemType.CASH_COUNT_REQUIRED.value
    item.status = "resolved"
    item.resolved_at = datetime.now(UTC)
    item.resolution_actor_type = "business"
    item.resolved_by_actor_id = tenant.actor_id
    item.resolution_code = "cash_count_recorded"
    db_session.commit()
    before = _count(db_session, tenant.business_id, WorkItemRow)
    body = _get(client, token).json()
    assert body["operator_state"] == "cash_count_required"
    assert body["primary_action"]["work_item_id"] is None
    assert _count(db_session, tenant.business_id, WorkItemRow) == before
    set_current_business_id(db_session, tenant.business_id)
    db_session.expire_all()
    open_count = db_session.scalar(
        select(func.count())
        .select_from(WorkItemRow)
        .where(WorkItemRow.business_id == tenant.business_id, WorkItemRow.status == "open")
    )
    assert int(open_count or 0) == 0
