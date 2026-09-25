from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent.providers.scripted import ScriptedLLMProvider
from app.agent.registrations import register_conversational_sale_tools
from app.agent.tools import ToolRegistry
from app.agent.ui_actions import UiActionRegistry
from app.application.queries.get_next_best_action import project_work_item
from app.application.workflows.initialize_open_work_items import initialize_open_today_work_items
from app.application.workflows.sync_daily_close_work_items import sync_daily_close_work_items
from app.domain.operations import (
    CashStatus,
    OperationalDayStatus,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkItemType,
    desired_open_type,
)
from app.domain.operations.work_item import (
    RESPONSIBLE_PARTY_BUSINESS,
    SOURCE_DAILY_CLOSE_RULE,
)
from app.infrastructure.persistence.audit import SqlAlchemyAuditService
from app.infrastructure.persistence.models import (
    AuditEventRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    WorkItemRow,
)
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository
from app.infrastructure.persistence.rls import set_current_business_id
from app.policies import PolicyRequest
from app.policies.engine import NBA_001, FoundationPolicyEngine
from tests.conftest import make_settings, seed_business
from tests.sale_cleanup import clear_tenant_sale_mutations
from tests.test_daily_close_confirmation import _confirm, _day, _post, _ready, _seed, _snapshots
from tests.test_daily_close_preparation import _cash_sale

_NOW = datetime(2026, 9, 24, 18, 0, tzinfo=UTC)


def _item(**overrides) -> WorkItem:
    base = dict(
        id=uuid4(),
        business_id=uuid4(),
        operational_day_id=uuid4(),
        type=WorkItemType.CASH_COUNT_REQUIRED,
        status=WorkItemStatus.OPEN,
        priority=WorkItemPriority.CRITICAL,
        responsible_party=RESPONSIBLE_PARTY_BUSINESS,
        reason_code="cash_count_missing",
        source=SOURCE_DAILY_CLOSE_RULE,
        evidence={
            "currency": "MXN",
            "expected_cash": "94.00",
            "sale_count": 2,
            "cash_status": "not_counted",
        },
        created_at=_NOW,
        updated_at=_NOW,
    )
    base.update(overrides)
    return WorkItem(**base)


def test_desired_set_is_one_type() -> None:
    assert desired_open_type(day_status=None, sale_count=0, cash_status=None) is None
    assert (
        desired_open_type(day_status=OperationalDayStatus.OPEN, sale_count=0, cash_status=CashStatus.NOT_COUNTED)
        is None
    )
    assert desired_open_type(day_status=OperationalDayStatus.CLOSED, sale_count=2, cash_status=CashStatus.SHORT) is None
    assert (
        desired_open_type(
            day_status=OperationalDayStatus.OPEN,
            sale_count=1,
            cash_status=CashStatus.NOT_COUNTED,
        )
        is WorkItemType.CASH_COUNT_REQUIRED
    )
    assert (
        desired_open_type(day_status=OperationalDayStatus.OPEN, sale_count=1, cash_status=CashStatus.SHORT)
        is WorkItemType.CASH_DIFFERENCE_REVIEW
    )
    assert (
        desired_open_type(day_status=OperationalDayStatus.OPEN, sale_count=1, cash_status=CashStatus.OVER)
        is WorkItemType.CASH_DIFFERENCE_REVIEW
    )
    assert (
        desired_open_type(day_status=OperationalDayStatus.OPEN, sale_count=1, cash_status=CashStatus.BALANCED)
        is WorkItemType.CLOSE_CONFIRMATION_REQUIRED
    )


def test_server_copy_uses_registered_sales_amounts() -> None:
    missing = project_work_item(_item())
    assert missing["title"] == "Cuenta el efectivo para continuar con el cierre."
    assert missing["reason"] == "Esperamos $94.00 en efectivo y todavía no hay un conteo."
    assert missing["actions"] == []
    assert missing["outcome_type"] == "daily_close_ready"
    assert missing["expires_at"] is None
    short = project_work_item(
        _item(
            type=WorkItemType.CASH_DIFFERENCE_REVIEW,
            priority=WorkItemPriority.HIGH,
            reason_code="cash_short",
            evidence={
                "currency": "MXN",
                "expected_cash": "94.00",
                "sale_count": 2,
                "cash_status": "short",
                "counted_cash": "80.00",
                "cash_difference": "-14.00",
                "cash_count_id": str(uuid4()),
            },
        )
    )
    assert short["title"] == "Hay un faltante de $14.00. Revisa la diferencia antes de confirmar el cierre."
    assert "las ventas registradas en Lumo" in short["reason"]
    assert "$94.00" in short["reason"]
    assert short["actions"] == [{"action_id": "closing.request@1"}]
    over = project_work_item(
        _item(
            type=WorkItemType.CASH_DIFFERENCE_REVIEW,
            priority=WorkItemPriority.HIGH,
            reason_code="cash_over",
            evidence={
                "currency": "MXN",
                "expected_cash": "94.00",
                "sale_count": 2,
                "cash_status": "over",
                "counted_cash": "104.00",
                "cash_difference": "10.00",
                "cash_count_id": str(uuid4()),
            },
        )
    )
    assert over["title"] == "Hay un sobrante de $10.00. Revisa la diferencia antes de confirmar el cierre."
    balanced = project_work_item(
        _item(
            type=WorkItemType.CLOSE_CONFIRMATION_REQUIRED,
            priority=WorkItemPriority.NORMAL,
            reason_code="close_confirmation_required",
            evidence={
                "currency": "MXN",
                "expected_cash": "94.00",
                "sale_count": 2,
                "cash_status": "balanced",
                "counted_cash": "94.00",
                "cash_difference": "0.00",
                "cash_count_id": str(uuid4()),
            },
        )
    )
    assert balanced["title"] == "La caja está cuadrada. El siguiente paso es cerrar la jornada."
    assert balanced["reversible"] is False


def test_pending_work_phrases_are_exact() -> None:
    provider = ScriptedLLMProvider()
    phrases = [
        "¿qué sigue?",
        "qué falta",
        "¿qué tengo pendiente?",
        "qué sigue con el cierre",
        "qué falta para cerrar",
        "qué falta para el cierre",
        "qué tengo pendiente para cerrar",
    ]
    for phrase in phrases:
        decision = provider.interpret(phrase, {}, [])
        assert decision.candidate_tool == "operational_day.next_best_action@1", phrase
    extended = provider.interpret("qué sigue con el cierre por favor", {}, [])
    assert extended.candidate_tool != "operational_day.next_best_action@1"
    assert provider.interpret("preparar el cierre", {}, []).candidate_tool == "closing.prepare@1"
    assert provider.interpret("ventas de hoy", {}, []).candidate_tool == "operational_day.summary@1"


def test_nba_policy_denies_model_amounts() -> None:
    engine = FoundationPolicyEngine()
    for arguments in ({"expected_cash": "1.00"}, {"priority": "critical"}, {"work_item_id": "x"}):
        decision = engine.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="operational_day.next_best_action@1",
                tool_registered=True,
                from_llm=True,
                arguments=arguments,
            )
        )
        assert decision.decision.value == "deny"
        assert decision.rule_ids == [NBA_001]
    allowed = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="operational_day.next_best_action@1",
            tool_registered=True,
            from_llm=True,
            arguments={},
        )
    )
    assert allowed.decision.value == "allow"
    registry = ToolRegistry()
    register_conversational_sale_tools(registry)
    tool = registry.get("operational_day.next_best_action@1")
    assert tool is not None
    assert tool.permission == "sale.create"
    assert tool.policy_id == "NBA-001"
    assert tool.side_effect == "read"
    assert tool.requires_idempotency is False
    assert UiActionRegistry().ids() == [
        "sale.pay.cash@1",
        "sale.pay.card@1",
        "sale.pay.transfer@1",
        "closing.request@1",
        "closing.confirm@1",
    ]


def _open_items(db_session, business_id: UUID) -> list[WorkItemRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(WorkItemRow)
            .where(WorkItemRow.business_id == business_id, WorkItemRow.status == "open")
            .order_by(WorkItemRow.created_at)
        ).all()
    )


def _all_items(db_session, business_id: UUID) -> list[WorkItemRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(WorkItemRow).where(WorkItemRow.business_id == business_id).order_by(WorkItemRow.created_at)
        ).all()
    )


def _audits(db_session, business_id: UUID, action: str) -> list[AuditEventRow]:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return list(
        db_session.scalars(
            select(AuditEventRow).where(AuditEventRow.business_id == business_id, AuditEventRow.action == action)
        ).all()
    )


def _count(db_session, business_id: UUID, model, **where) -> int:
    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    stmt = select(func.count()).select_from(model).where(model.business_id == business_id)
    for column, value in where.items():
        stmt = stmt.where(getattr(model, column) == value)
    return int(db_session.scalar(stmt) or 0)


def _nba(client: TestClient, token: str):
    return client.get(
        "/api/v1/operational-days/current/next-best-action",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_first_sale_creates_one_count_item_and_reads_are_pure(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    empty = _nba(client, token)
    assert empty.status_code == 200
    assert empty.json() == {
        "operational_day_id": None,
        "day_status": None,
        "pending_count": 0,
        "next_best_action": None,
    }
    _cash_sale(client, token, "nba-first", "900gr zanahoria")
    rows = _open_items(db_session, tenant.business_id)
    assert len(rows) == 1
    assert rows[0].type == "cash_count_required"
    assert rows[0].priority == "critical"
    assert rows[0].responsible_party == "business"
    assert rows[0].reason_code == "cash_count_missing"
    assert rows[0].source == "daily_close_rule"
    first_id = rows[0].id
    updated_at = rows[0].updated_at
    audits_before = _count(db_session, tenant.business_id, AuditEventRow)
    idem_before = _count(db_session, tenant.business_id, IdempotencyRecordRow)
    outbox_before = _count(db_session, tenant.business_id, OutboxEventRow)
    first = _nba(client, token)
    second = _nba(client, token)
    assert first.status_code == 200
    body = first.json()
    assert body["pending_count"] == 1
    assert body["next_best_action"]["work_item_id"] == str(first_id)
    assert body["next_best_action"]["type"] == "cash_count_required"
    assert body["next_best_action"]["actions"] == []
    assert "context_token" not in first.text
    assert second.json()["next_best_action"]["work_item_id"] == str(first_id)
    assert _count(db_session, tenant.business_id, AuditEventRow) == audits_before
    assert _count(db_session, tenant.business_id, IdempotencyRecordRow) == idem_before
    assert _count(db_session, tenant.business_id, OutboxEventRow) == outbox_before
    sync_daily_close_work_items(
        identities=IdentityRepository(db_session),
        operations=OperationsRepository(db_session),
        audit=SqlAlchemyAuditService(db_session),
        tenant=tenant,
        correlation_id="noop",
        idempotency_key=None,
        route_or_tool="sale.commit@1",
    )
    db_session.commit()
    again = _open_items(db_session, tenant.business_id)
    assert again[0].id == first_id
    assert again[0].updated_at == updated_at
    _cash_sale(client, token, "nba-second", "1kg tomate")
    after_second = _open_items(db_session, tenant.business_id)
    assert len(after_second) == 1
    assert after_second[0].id == first_id
    assert after_second[0].evidence["sale_count"] == 2
    idem_before_read = _count(db_session, tenant.business_id, IdempotencyRecordRow)
    phrase = _post(client, token, "¿qué sigue?", "nba-phrase-1", "conv-nba-phrase")
    assert phrase.status_code == 200, phrase.text
    assert "Esperamos $" in phrase.json()["text"]
    assert phrase.json()["ui"][0]["component"] == "next_best_action"
    assert phrase.json()["ui"][0]["fallback_text"] == phrase.json()["text"]
    repeated = _post(client, token, "qué falta", "nba-phrase-2", "conv-nba-phrase")
    assert repeated.json()["ui"][0]["data"]["work_item_id"] == str(first_id)
    assert _count(db_session, tenant.business_id, IdempotencyRecordRow) == idem_before_read
    paths = {getattr(route, "path", "") for route in client.app.routes}
    assert "/api/v1/operational-days/current/work-items" not in paths
    assert not any("work-items" in path for path in paths)


def test_count_transitions_and_short_close(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation, requested = _ready(client, token, "nba-short", counted="20.00")
    open_rows = _open_items(db_session, tenant.business_id)
    assert len(open_rows) == 1
    assert open_rows[0].type == "cash_difference_review"
    assert open_rows[0].reason_code == "cash_short"
    assert not any(row.type == "close_confirmation_required" for row in _all_items(db_session, tenant.business_id))
    projection = _nba(client, token).json()
    assert projection["pending_count"] == 1
    assert projection["next_best_action"]["type"] == "cash_difference_review"
    assert projection["next_best_action"]["actions"] == [{"action_id": "closing.request@1"}]
    assert "context_token" not in requested.json()["ui"][0]["data"].get("next_best_action", {})
    card = _post(client, token, "qué sigue", "nba-short-phrase", "conv-nba-short").json()["ui"][0]
    assert card["component"] == "next_best_action"
    assert [action["action_id"] for action in card["actions"]] == ["closing.request@1"]
    assert card["actions"][0]["context_token"]
    difference_id = open_rows[0].id
    created_audits = _audits(db_session, tenant.business_id, "work_item.created")
    assert created_audits
    resolved_before = len(_audits(db_session, tenant.business_id, "work_item.resolved"))
    closed = _confirm(client, token, "nba-short", confirmation)
    assert closed.status_code == 200, closed.text
    snapshot = _snapshots(db_session, tenant.business_id)[0]
    assert snapshot.cash_difference == Decimal("-2.50")
    assert snapshot.cash_status == "short"
    assert _day(db_session, tenant.business_id).status == "closed"
    history = _all_items(db_session, tenant.business_id)
    difference = next(row for row in history if row.id == difference_id)
    assert difference.status == "resolved"
    assert difference.resolution_code == "day_closed"
    assert difference.resolution_actor_type == "business"
    assert difference.resolved_by_actor_id == tenant.actor_id
    assert not any(row.type == "close_confirmation_required" for row in history)
    assert _open_items(db_session, tenant.business_id) == []
    resolve_audits = _audits(db_session, tenant.business_id, "work_item.resolved")
    assert len(resolve_audits) == resolved_before + 1
    close_audit = next(row for row in resolve_audits if row.after_payload["work_item_id"] == str(difference_id) and row.after_payload["resolution_code"] == "day_closed")
    assert close_audit.after_payload["resolution_actor_type"] == "business"
    assert close_audit.after_payload["resolved_by_actor_id"] == str(tenant.actor_id)
    assert close_audit.actor_id == tenant.actor_id
    reread = _nba(client, token).json()
    assert reread["pending_count"] == 0
    assert reread["next_best_action"] is None
    assert _count(db_session, tenant.business_id, OutboxEventRow, event_type="work_item.created") == 0
    replay = _confirm(client, token, "nba-short", confirmation, key="nba-short-confirm")
    assert replay.status_code == 200
    assert len(_audits(db_session, tenant.business_id, "work_item.resolved")) == len(resolve_audits)


def test_balanced_over_and_system_resolution(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "nba-bal", "900gr zanahoria")
    counted = _post(client, token, "conté 22.50", "nba-bal-count", "conv-nba-bal")
    assert counted.status_code == 200, counted.text
    open_rows = _open_items(db_session, tenant.business_id)
    assert len(open_rows) == 1
    assert open_rows[0].type == "close_confirmation_required"
    assert _nba(client, token).json()["pending_count"] == 1
    count_resolved = next(row for row in _all_items(db_session, tenant.business_id) if row.type == "cash_count_required")
    assert count_resolved.resolution_code == "cash_count_recorded"
    assert count_resolved.resolution_actor_type == "business"
    assert count_resolved.resolved_by_actor_id == tenant.actor_id
    over = _post(client, token, "conté 25.00", "nba-over", "conv-nba-bal")
    assert over.status_code == 200, over.text
    current = _open_items(db_session, tenant.business_id)
    assert len(current) == 1
    assert current[0].type == "cash_difference_review"
    assert current[0].reason_code == "cash_over"
    close_resolved = next(
        row
        for row in _all_items(db_session, tenant.business_id)
        if row.type == "close_confirmation_required" and row.status == "resolved"
    )
    assert close_resolved.resolution_code == "cash_unbalanced"
    assert close_resolved.resolution_actor_type == "system"
    assert close_resolved.resolved_by_actor_id is None
    unbalanced_audit = next(
        row
        for row in _audits(db_session, tenant.business_id, "work_item.resolved")
        if row.after_payload["resolution_code"] == "cash_unbalanced"
    )
    assert unbalanced_audit.after_payload["resolution_actor_type"] == "system"
    assert "resolved_by_actor_id" not in unbalanced_audit.after_payload
    assert unbalanced_audit.actor_id is None
    short = _post(client, token, "conté 20.00", "nba-flip", "conv-nba-bal")
    assert short.status_code == 200, short.text
    flipped = _open_items(db_session, tenant.business_id)
    assert len(flipped) == 1
    assert flipped[0].id == current[0].id
    assert flipped[0].reason_code == "cash_short"
    balanced = _post(client, token, "conté 22.50", "nba-rebalance", "conv-nba-bal")
    assert balanced.status_code == 200, balanced.text
    reopened = _open_items(db_session, tenant.business_id)
    assert len(reopened) == 1
    assert reopened[0].type == "close_confirmation_required"
    settled = next(row for row in _all_items(db_session, tenant.business_id) if row.id == current[0].id)
    assert settled.status == "resolved"
    assert settled.resolution_code == "cash_balanced"
    assert settled.resolution_actor_type == "system"
    assert settled.resolved_by_actor_id is None
    later = _post(client, token, "conté 20.00", "nba-new-gen", "conv-nba-bal")
    assert later.status_code == 200, later.text
    generated = _open_items(db_session, tenant.business_id)
    assert len(generated) == 1
    assert generated[0].type == "cash_difference_review"
    assert generated[0].id != current[0].id
    assert settled.status == "resolved"


def test_reads_and_initializer_do_not_invent_work(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "nba-init", "900gr zanahoria")
    original = _open_items(db_session, tenant.business_id)[0]
    updated_at = original.updated_at
    audit_count = _count(db_session, tenant.business_id, AuditEventRow)
    prepared = _post(client, token, "preparar el cierre", "nba-prep", "conv-nba-init")
    assert prepared.status_code == 200
    assert "next_best_action" not in str(prepared.json()["ui"])
    summary = _post(client, token, "ventas de hoy", "nba-sum", "conv-nba-init")
    assert summary.status_code == 200
    assert all(card["component"] != "next_best_action" for card in summary.json()["ui"])
    exported = client.get(
        "/api/v1/operational-days/current/sales-export?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert exported.status_code == 200
    assert _open_items(db_session, tenant.business_id)[0].updated_at == updated_at
    assert _count(db_session, tenant.business_id, AuditEventRow) == audit_count
    set_current_business_id(db_session, tenant.business_id)
    db_session.execute(WorkItemRow.__table__.delete().where(WorkItemRow.business_id == tenant.business_id))
    db_session.execute(
        AuditEventRow.__table__.delete().where(
            AuditEventRow.business_id == tenant.business_id,
            AuditEventRow.action.in_(("work_item.created", "work_item.resolved")),
        )
    )
    db_session.commit()
    admin_url = make_settings().sqlalchemy_admin_url
    inserted = initialize_open_today_work_items(admin_url=admin_url)
    assert inserted >= 1
    restored = _open_items(db_session, tenant.business_id)
    assert len(restored) == 1
    assert restored[0].type == "cash_count_required"
    created = _audits(db_session, tenant.business_id, "work_item.created")
    assert len(created) == 1
    assert created[0].actor_id is None
    assert created[0].route_or_tool == "work_item.bootstrap"
    assert created[0].after_payload["origin"] == "rollout_bootstrap"
    again = initialize_open_today_work_items(admin_url=admin_url)
    assert again == 0
    assert len(_open_items(db_session, tenant.business_id)) == 1
    assert len(_audits(db_session, tenant.business_id, "work_item.created")) == 1
    quiet = _nba(client, token)
    assert quiet.json()["next_best_action"]["work_item_id"] == str(restored[0].id)
    assert len(_audits(db_session, tenant.business_id, "work_item.created")) == 1
    business_b, _user_b, _token_b = seed_business(db_session, name="Other")
    set_current_business_id(db_session, business_b)
    db_session.expire_all()
    hidden = db_session.scalars(select(WorkItemRow)).all()
    assert all(row.business_id == business_b for row in hidden)
    clear_tenant_sale_mutations(db_session, business_b)


def test_failed_commit_rolls_back_the_work_item(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    conversation_id = "conv-nba-fail"
    added = _post(client, token, "900gr zanahoria", "nba-fail-add", conversation_id)
    assert added.status_code == 200, added.text
    totaled = _post(client, token, "totalizar", "nba-fail-tot", conversation_id)
    assert totaled.status_code == 200, totaled.text
    failed = _post(
        client,
        token,
        "efectivo",
        "nba-fail-pay",
        conversation_id,
        **{"X-Debug-Fail-After-Write": "1"},
    )
    assert failed.status_code == 500
    assert _all_items(db_session, tenant.business_id) == []
    assert _audits(db_session, tenant.business_id, "work_item.created") == []


def test_empty_pending_phrase_has_no_card(client: TestClient, db_session) -> None:
    _tenant, token = _seed(db_session)
    response = _post(client, token, "qué tengo pendiente", "nba-empty", "conv-nba-empty")
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "No hay un paso pendiente para el cierre de hoy."
    assert response.json()["ui"] == []
    unsupported = _post(client, token, "qué sigue con el cierre por favor", "nba-please", "conv-nba-empty")
    assert unsupported.json()["ui"] == []
    assert "operational_day.next_best_action" not in unsupported.text
