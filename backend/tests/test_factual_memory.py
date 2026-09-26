from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.agent.providers.scripted import FACTUAL_SCOPE_TEXT, ScriptedLLMProvider, normalize_closed_phrase
from app.agent.registrations import BUSINESS_FACTS, register_conversational_sale_tools
from app.agent.tools import ToolRegistry
from app.agent.ui_actions import UiActionRegistry
from app.application.queries.get_factual_memory import FactualMemoryService
from app.domain.operations import business_date_for
from app.domain.operations.factual_memory import FactualMemoryQuery, FactualQueryType
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.models import (
    AuditEventRow,
    BusinessEventRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutboxEventRow,
    SourceCoverageRecordRow,
)
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository
from app.policies import PolicyRequest
from app.policies.engine import FoundationPolicyEngine
from tests.conftest import make_settings, postgres_available, seed_business
from tests.test_daily_close_confirmation import _confirm, _post, _ready, _seed
from tests.test_daily_close_preparation import _cash_sale

pytestmark = pytest.mark.skipif(
    not postgres_available(make_settings()),
    reason="PostgreSQL is not available",
)

_NOW = datetime(2026, 9, 26, 18, 0, tzinfo=UTC)
_BOUNDARY = datetime(2026, 9, 26, 5, 30, tzinfo=UTC)


def test_memory_tool_is_read_only_and_actions_stay_closed() -> None:
    assert BUSINESS_FACTS.qualified_id == "memory.business_facts@1"
    assert BUSINESS_FACTS.version == 1
    assert BUSINESS_FACTS.side_effect == "read"
    assert BUSINESS_FACTS.requires_idempotency is False
    assert BUSINESS_FACTS.permission == "sale.create"
    assert BUSINESS_FACTS.policy_id == "MEM-001"
    registry = ToolRegistry()
    register_conversational_sale_tools(registry)
    assert registry.is_registered("memory.business_facts@1")
    assert not registry.is_registered("memory.query_events@1")
    actions = UiActionRegistry()
    assert actions.ids() == [
        "sale.pay.cash@1",
        "sale.pay.card@1",
        "sale.pay.transfer@1",
        "closing.request@1",
        "closing.confirm@1",
    ]


def test_mem_001_allows_only_approved_shapes() -> None:
    engine = FoundationPolicyEngine()
    allowed = _policy(engine, {"query_type": "day_summary", "business_date": "2026-09-24"})
    assert allowed.decision.value == "allow"
    assert allowed.rule_ids == ["MEM-001"]
    assert _policy(engine, {"query_type": "latest_close"}).decision.value == "allow"
    assert _policy(engine, {"query_type": "recent_cash_differences", "recent_days": 1}).decision.value == "allow"
    assert _policy(engine, {"query_type": "recent_cash_differences", "recent_days": 30}).decision.value == "allow"
    denied = [
        {"query_type": "day_summary"},
        {"query_type": "day_summary", "business_date": "2026-09-24", "business_id": "x"},
        {"query_type": "sales_summary", "business_date": "2026-09-24", "query": "ventas"},
        {"query_type": "sales_summary", "business_date": "2026-09-24", "sql": "select 1"},
        {"query_type": "sales_summary", "business_date": "2026-09-24", "filters": {}},
        {"query_type": "day_events", "business_date": "2026-09-24", "event_type": "sale_confirmed"},
        {"query_type": "latest_close", "business_date": "2026-09-24"},
        {"query_type": "latest_close", "recent_days": 7},
        {"query_type": "recent_cash_differences", "recent_days": 0},
        {"query_type": "recent_cash_differences", "recent_days": 31},
        {"query_type": "recent_cash_differences", "recent_days": True},
        {"query_type": "day_summary", "business_date": "2026-02-31"},
    ]
    for arguments in denied:
        decision = _policy(engine, arguments)
        assert decision.decision.value == "deny", arguments
        assert decision.reason_code == "factual_memory_arguments_denied"


def test_closed_phrases_route_to_factual_memory_or_stay_on_summary() -> None:
    provider = ScriptedLLMProvider()
    day = {
        "¿Qué pasó hoy?": ("day_summary", "today"),
        "que paso ayer": ("day_summary", "yesterday"),
        "¿Cuánto vendí hoy?": ("sales_summary", "today"),
        "cuantas ventas tuve hoy": ("sales_summary", "today"),
        "cuanto vendi ayer": ("sales_summary", "yesterday"),
        "¿Cuántas ventas tuve ayer?": ("sales_summary", "yesterday"),
        "¿Cómo cerré hoy?": ("close_summary", "today"),
        "como cerre ayer": ("close_summary", "yesterday"),
        "¿Hubo diferencia de caja?": ("cash_summary", "today"),
        "hay diferencia de caja": ("cash_summary", "today"),
        "¿Qué eventos hubo hoy?": ("day_events", "today"),
        "que eventos hubo ayer": ("day_events", "yesterday"),
    }
    for phrase, expected in day.items():
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "factual_memory", phrase
        assert decision.candidate_tool == "memory.business_facts@1"
        assert decision.factual_query_type == expected[0]
        assert decision.factual_scope == expected[1]
    for phrase in ("¿Cuál fue mi último cierre?", "que paso en el ultimo cierre"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.factual_query_type == "latest_close"
        assert decision.factual_scope == "latest"
        assert decision.factual_business_date is None
        assert decision.factual_recent_days is None
    recent = provider.interpret("he tenido diferencias de caja últimamente", {}, [])
    assert recent.factual_query_type == "recent_cash_differences"
    assert recent.factual_recent_days == 7
    spoken = provider.interpret("¿Qué pasó el 24 de septiembre?", {}, [])
    assert spoken.factual_query_type == "day_summary"
    assert spoken.factual_scope == "date"
    assert spoken.factual_month == 9
    assert spoken.factual_day == 24
    assert spoken.factual_business_date is None
    dated = provider.interpret("que paso el 24 de septiembre de 2025", {}, [])
    assert dated.factual_business_date == "2025-09-24"
    iso = provider.interpret("que paso el 2026-09-24", {}, [])
    assert iso.factual_business_date == "2026-09-24"
    for phrase in (
        "como vamos hoy",
        "ventas de hoy",
        "cuanto vendimos hoy",
        "¿Cómo vamos hoy?",
    ):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "day_summary", phrase
        assert decision.candidate_tool == "operational_day.summary@1"
    unknown = provider.interpret("hola", {}, [])
    assert unknown.candidate_tool != "memory.business_facts@1"
    assert unknown.intent == "add_sale_item"
    sale = provider.interpret("900gr zanahoria", {}, [])
    assert sale.intent == "add_sale_item"


def test_exact_cuanto_vendi_hoy_is_sales_summary_not_a_product() -> None:
    phrase = "¿Cuánto vendí hoy?"
    assert normalize_closed_phrase(phrase) == "cuanto vendi hoy"
    assert normalize_closed_phrase("¿Cuánto vendimos hoy?") == "cuanto vendimos hoy"
    decision = ScriptedLLMProvider().interpret(phrase, {}, [])
    assert decision.intent == "factual_memory"
    assert decision.candidate_tool == "memory.business_facts@1"
    assert decision.factual_query_type == "sales_summary"
    assert decision.factual_scope == "today"
    assert decision.clarification_question is None
    vendimos = ScriptedLLMProvider().interpret("¿Cuánto vendimos hoy?", {}, [])
    assert vendimos.intent == "day_summary"
    assert vendimos.candidate_tool == "operational_day.summary@1"
    for phrase, tool in (
        ("¿Ventas de hoy?", "operational_day.summary@1"),
        ("¿Cómo vamos hoy?", "operational_day.summary@1"),
        ("¿Cuántas ventas tuve hoy?", "memory.business_facts@1"),
    ):
        routed = ScriptedLLMProvider().interpret(phrase, {}, [])
        assert routed.candidate_tool == tool, phrase


def test_exact_cuanto_vendi_hoy_on_the_conversation_endpoint(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "mem-exact", "900gr zanahoria")
    before = _write_counts(db_session, tenant.business_id)
    response = _post(client, token, "¿Cuánto vendí hoy?", "mem-exact-sales", "conv-mem-exact")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"].startswith("Según las ventas registradas en Lumo")
    assert "22.50" in body["text"]
    assert "Puedo registrar un producto" not in body["text"]
    assert body["ui"] == []
    assert _write_counts(db_session, tenant.business_id) == before
    today = business_date_for(utcnow(), "America/Mexico_City").isoformat()
    arguments = {"query_type": "sales_summary", "business_date": today}
    policy = _policy(FoundationPolicyEngine(), arguments)
    assert policy.decision.value == "allow"
    assert policy.rule_ids == ["MEM-001"]
    assert "business_id" not in arguments
    vendimos = _post(client, token, "¿Cuánto vendimos hoy?", "mem-exact-vendimos", "conv-mem-exact")
    assert vendimos.status_code == 200, vendimos.text
    assert vendimos.json()["text"].startswith("Hoy ")
    assert vendimos.json()["ui"][0]["component"] == "operational_day_summary"
    ventas = _post(client, token, "¿Ventas de hoy?", "mem-exact-ventas", "conv-mem-exact")
    assert ventas.json()["text"].startswith("Hoy ")
    assert ventas.json()["ui"][0]["component"] == "operational_day_summary"
    vamos = _post(client, token, "¿Cómo vamos hoy?", "mem-exact-vamos", "conv-mem-exact")
    assert vamos.json()["text"].startswith("Hoy ")
    assert vamos.json()["ui"][0]["component"] == "operational_day_summary"
    tuve = _post(client, token, "¿Cuántas ventas tuve hoy?", "mem-exact-tuve", "conv-mem-exact")
    assert tuve.json()["text"].startswith("Según las ventas registradas en Lumo")
    assert tuve.json()["ui"] == []


def test_unsupported_history_does_not_select_a_tool() -> None:
    provider = ScriptedLLMProvider()
    for phrase in (
        "el trimestre pasado",
        "este año",
        "el año pasado",
        "qué pasó el trimestre pasado",
        "que paso este ano",
        "qué vendí este año",
        "que vendi el ano pasado",
        "que paso el 2026-02-31",
        "que paso el 31 de febrero",
    ):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "factual_memory_unsupported", phrase
        assert decision.candidate_tool is None
        assert decision.clarification_question == FACTUAL_SCOPE_TEXT


def test_open_day_summary_sales_and_cash(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _clocked_sale(client, token, "mem-open", _NOW)
    summary = _ask(client, token, "¿Qué pasó hoy?", "mem-open-sum", now=_NOW)
    assert summary.startswith("En las operaciones registradas en Lumo")
    assert "22.50" in summary
    assert "No vendiste" not in summary
    sales = _ask(client, token, "¿Cuánto vendí hoy?", "mem-open-sales", now=_NOW)
    assert sales.startswith("Según las ventas registradas en Lumo")
    assert "22.50" in sales
    missing_cash = _ask(client, token, "¿Hubo diferencia de caja?", "mem-open-cash-missing", now=_NOW)
    assert missing_cash == "No encuentro un conteo de efectivo registrado en Lumo para ese día."
    counted = _post(
        client,
        token,
        "conté 10.00",
        "mem-open-count",
        "conv-mem-open",
        **{"X-Debug-Now": _NOW.isoformat()},
    )
    assert counted.status_code == 200, counted.text
    cash = _ask(client, token, "hay diferencia de caja", "mem-open-cash", now=_NOW)
    assert cash.startswith("En las operaciones registradas en Lumo")
    assert "22.50" in cash
    assert "10.00" in cash
    assert "Faltante" in cash
    service = _service(db_session)
    result = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.CASH_SUMMARY, business_date=_today()),
        now=_NOW,
    )
    assert result.facts is not None
    assert result.facts.cash_status == "short"
    assert result.empty_reason is None
    assert result.source_coverage["basis"] == "recorded_operations"
    assert result.source_coverage["merchant_source_declaration"] is None
    assert "complete" not in result.source_coverage
    again = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.DAY_SUMMARY, business_date=_today()),
        now=_NOW,
    )
    repeated = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.DAY_SUMMARY, business_date=_today()),
        now=_NOW,
    )
    assert again.to_dict() == repeated.to_dict()
    assert again.facts is not None
    assert again.facts.sale_count == 1
    assert again.facts.close_status == "not_completed"
    assert again.facts.cash_status == "short"
    assert again.empty_reason is None


def test_day_without_sales_and_without_a_day(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    before = _day_count(db_session, tenant.business_id)
    future = _ask(client, token, "que paso el 2099-01-01", "mem-future", now=_NOW)
    assert future == FACTUAL_SCOPE_TEXT
    assert _day_count(db_session, tenant.business_id) == before
    missing = _ask(client, token, "que paso el 2026-09-20", "mem-missing", now=_NOW)
    assert "No encuentro" in missing
    assert "registrado en Lumo" in missing
    assert _day_count(db_session, tenant.business_id) == before
    _open_day(db_session, tenant)
    empty_sales = _ask(client, token, "cuantas ventas tuve hoy", "mem-empty-sales", now=_NOW)
    assert empty_sales == "No encuentro ventas registradas en Lumo para ese día."
    service = _service(db_session)
    events = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.DAY_EVENTS, business_date=_today()),
        now=_NOW,
    )
    assert events.empty_reason is not None
    assert events.empty_reason.value == "no_matching_facts"
    no_day = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.DAY_EVENTS, business_date=_today() - timedelta(days=3)),
        now=_NOW,
    )
    assert no_day.empty_reason is not None
    assert no_day.empty_reason.value == "no_operational_day"
    assert no_day.source_coverage is None


def test_closed_day_snapshot_latest_and_differences(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    short_token, _requested = _ready(client, token, "mem-short", counted="10.00")
    closed = _confirm(client, token, "mem-short", short_token)
    assert closed.status_code == 200, closed.text
    assert closed.json()["text"].startswith("Cierre confirmado")
    close_text = _ask(client, token, "¿Cómo cerré hoy?", "mem-close")
    assert close_text.startswith("El cierre registrado")
    assert "22.50" in close_text
    assert "Faltante" in close_text
    service = _service(db_session)
    today = business_date_for(utcnow(), "America/Mexico_City")
    closed_summary = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.CLOSE_SUMMARY, business_date=today),
        now=_NOW,
    )
    assert closed_summary.facts is not None
    assert closed_summary.facts.gross_sales_total == "22.50"
    assert closed_summary.facts.cash_status == "short"
    assert closed_summary.facts.outcome_status == "completed"
    assert closed_summary.empty_reason is None
    first = closed_summary.to_dict()
    second = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.CLOSE_SUMMARY, business_date=today),
        now=_NOW,
    ).to_dict()
    assert first == second
    day_summary = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.DAY_SUMMARY, business_date=today),
        now=_NOW,
    )
    assert day_summary.facts is not None
    assert day_summary.facts.close_status == "completed"
    assert day_summary.facts.gross_sales_total == "22.50"
    assert [event.event_type for event in day_summary.events] == sorted(
        (event.event_type for event in day_summary.events),
        key=lambda _item: 0,
    )
    assert day_summary.events == tuple(sorted(day_summary.events, key=lambda event: (event.occurred_at, event.event_id)))
    sales = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.SALES_SUMMARY, business_date=today),
        now=_NOW,
    )
    assert sales.facts is not None
    assert sales.facts.sale_count == 1
    assert sales.events == ()
    latest = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.LATEST_CLOSE),
        now=_NOW,
    )
    assert latest.facts is not None
    assert latest.business_date == today
    recent = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.RECENT_CASH_DIFFERENCES, recent_days=7),
        now=_NOW,
    )
    assert recent.source_coverage is None
    assert recent.facts is not None
    assert len(recent.facts) == 1
    assert recent.facts[0].cash_status == "short"
    other_business, _other_user, other_token = seed_business(db_session, name="Otra")
    hidden = FactualMemoryService(
        identities=IdentityRepository(db_session),
        operations=OperationsRepository(db_session),
    ).execute(
        tenant=TenantContext(business_id=other_business, actor_id=_other_user),
        query=FactualMemoryQuery(query_type=FactualQueryType.LATEST_CLOSE),
        now=_NOW,
    )
    assert hidden.empty_reason is not None
    assert hidden.empty_reason.value == "no_completed_close"
    foreign = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {other_token}"})
    assert foreign.status_code == 200, foreign.text
    assert foreign.json()["events"] == []


def test_balanced_close_is_excluded_and_open_count_is_not_a_difference(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    confirmation = _clocked_ready(client, token, "mem-balanced", _NOW, counted="22.50")
    confirmed = _confirm(client, token, "mem-balanced", confirmation, **{"X-Debug-Now": _NOW.isoformat()})
    assert confirmed.status_code == 200, confirmed.text
    service = _service(db_session)
    recent = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.RECENT_CASH_DIFFERENCES, recent_days=7),
        now=_NOW,
    )
    assert recent.empty_reason is not None
    assert recent.empty_reason.value == "no_matching_facts"
    assert recent.facts is None
    _post(client, token, "conté 1.00", "mem-open-diff", "conv-mem-open-diff", **{"X-Debug-Now": _BOUNDARY.isoformat()})
    still = service.execute(
        tenant=tenant,
        query=FactualMemoryQuery(query_type=FactualQueryType.RECENT_CASH_DIFFERENCES, recent_days=7),
        now=_NOW,
    )
    assert still.empty_reason is not None
    assert still.empty_reason.value == "no_matching_facts"


def test_existing_summary_phrase_stays_on_hoy(client: TestClient, db_session) -> None:
    _tenant, token = _seed(db_session)
    _cash_sale(client, token, "mem-hoy", "900gr zanahoria")
    summary = _post(client, token, "como vamos hoy", "mem-hoy-sum", "conv-mem-hoy")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["text"].startswith("Hoy ")
    assert body["ui"][0]["component"] == "operational_day_summary"
    prepare = _post(client, token, "preparar el cierre", "mem-hoy-prep", "conv-mem-hoy")
    assert prepare.status_code == 200, prepare.text
    assert prepare.json()["ui"][0]["component"] == "daily_close_preparation"


def test_utc_boundary_uses_business_date(client: TestClient, db_session) -> None:
    _tenant, token = _seed(db_session)
    header = {"X-Debug-Now": _BOUNDARY.isoformat()}
    added = _post(client, token, "900gr zanahoria", "mem-boundary-add", "conv-mem-boundary", **header)
    assert added.status_code == 200, added.text
    totaled = _post(client, token, "totalizar", "mem-boundary-tot", "conv-mem-boundary", **header)
    assert totaled.status_code == 200, totaled.text
    paid = _post(client, token, "efectivo", "mem-boundary-pay", "conv-mem-boundary", **header)
    assert paid.status_code == 200, paid.text
    text = _ask(client, token, "que paso hoy", "mem-boundary-ask", now=_BOUNDARY)
    assert "2026-09-25" not in text or "2026-09-26" not in text
    service = _service(db_session)
    result = service.execute(
        tenant=_tenant,
        query=FactualMemoryQuery(
            query_type=FactualQueryType.DAY_SUMMARY,
            business_date=business_date_for(_BOUNDARY, "America/Mexico_City"),
        ),
        now=_BOUNDARY,
    )
    assert result.business_date is not None
    assert result.business_date.isoformat() == "2026-09-25"
    assert result.facts is not None
    assert result.facts.sale_count == 1


def test_timeline_window_cursor_and_no_writes(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "mem-time", "900gr zanahoria")
    counted = _post(client, token, "conté 22.50", "mem-time-count", "conv-mem-time")
    assert counted.status_code == 200, counted.text
    before = _write_counts(db_session, tenant.business_id)
    response = client.get("/api/v1/memory/events", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["business_today"] == business_date_for(utcnow(), "America/Mexico_City").isoformat()
    yesterday = business_date_for(utcnow(), "America/Mexico_City") - timedelta(days=1)
    assert body["business_yesterday"] == yesterday.isoformat()
    assert body["events"]
    assert body["events"] == sorted(body["events"], key=lambda event: (event["occurred_at"], event["event_id"]), reverse=True)
    assert body["events"][0]["local_time"]
    assert len(body["events"][0]["local_time"]) == 5
    assert _write_counts(db_session, tenant.business_id) == before
    limited = client.get("/api/v1/memory/events?limit=1", headers={"Authorization": f"Bearer {token}"})
    assert limited.status_code == 200, limited.text
    page = limited.json()
    assert len(page["events"]) == 1
    assert page["next_cursor"]
    older = client.get(
        "/api/v1/memory/events",
        params={"limit": 20, "before": page["next_cursor"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert older.status_code == 200, older.text
    assert all(event["event_id"] != page["events"][0]["event_id"] for event in older.json()["events"])
    for limit in (0, 51):
        invalid = client.get(
            "/api/v1/memory/events",
            params={"limit": limit},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert invalid.status_code == 422, invalid.text
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"
    malformed = client.get(
        "/api/v1/memory/events",
        params={"before": "not-a-cursor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"
    outside = client.get(
        "/api/v1/memory/events",
        params={"before": _cursor(datetime(2020, 1, 1, tzinfo=UTC))},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert outside.status_code == 200, outside.text
    assert outside.json()["events"] == []
    assert outside.json()["next_cursor"] is None
    rejected = client.get(
        "/api/v1/memory/events",
        params={"event_type": "sale_confirmed"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rejected.status_code == 422
    assert _write_counts(db_session, tenant.business_id) == before


def test_factual_read_does_not_reserve_idempotency(client: TestClient, db_session) -> None:
    tenant, token = _seed(db_session)
    _cash_sale(client, token, "mem-idem", "900gr zanahoria")
    before = _count(db_session, tenant.business_id, IdempotencyRecordRow)
    _ask(client, token, "cuanto vendi hoy", "mem-idem-read")
    assert _count(db_session, tenant.business_id, IdempotencyRecordRow) == before


def _policy(engine: FoundationPolicyEngine, arguments: dict):
    return engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="memory.business_facts@1",
            tool_registered=True,
            from_llm=True,
            arguments=arguments,
        )
    )


def _service(db_session) -> FactualMemoryService:
    return FactualMemoryService(
        identities=IdentityRepository(db_session),
        operations=OperationsRepository(db_session),
    )


def _today():
    return business_date_for(_NOW, "America/Mexico_City")


def _clocked_sale(client: TestClient, token: str, prefix: str, now: datetime) -> None:
    header = {"X-Debug-Now": now.isoformat()}
    conversation = f"conv-{prefix}"
    for message, key in (
        ("900gr zanahoria", f"{prefix}-add"),
        ("totalizar", f"{prefix}-tot"),
        ("efectivo", f"{prefix}-pay"),
    ):
        response = _post(client, token, message, key, conversation, **header)
        assert response.status_code == 200, response.text


def _clocked_ready(client: TestClient, token: str, prefix: str, now: datetime, counted: str) -> str:
    header = {"X-Debug-Now": now.isoformat()}
    _clocked_sale(client, token, prefix, now)
    counted_response = _post(client, token, f"conté {counted}", f"{prefix}-count", f"conv-{prefix}", **header)
    assert counted_response.status_code == 200, counted_response.text
    requested = _post(client, token, "cerrar el día", f"{prefix}-req", f"conv-{prefix}", **header)
    assert requested.status_code == 200, requested.text
    token_value = requested.json()["ui"][0]["data"]["confirmation_token"]
    assert isinstance(token_value, str) and token_value
    return token_value


def _open_day(db_session, tenant: TenantContext) -> None:
    from app.domain.shared.ids import new_uuid7

    OperationsRepository(db_session).ensure_open_day(
        tenant=tenant,
        business_date=_today(),
        timezone_name="America/Mexico_City",
        day_id=new_uuid7(),
        opened_at=_NOW,
    )
    db_session.commit()


def _ask(client: TestClient, token: str, message: str, key: str, now: datetime | None = None) -> str:
    headers = {}
    if now is not None:
        headers["X-Debug-Now"] = now.isoformat()
    response = _post(client, token, message, key, f"conv-{key}", **headers)
    assert response.status_code == 200, response.text
    assert response.json()["ui"] == []
    return response.json()["text"]


def _day_count(db_session, business_id: UUID) -> int:
    return _count(db_session, business_id, OperationalDayRow)


def _count(db_session, business_id: UUID, model) -> int:
    from app.infrastructure.persistence.rls import set_current_business_id

    set_current_business_id(db_session, business_id)
    db_session.expire_all()
    return int(db_session.scalar(select(func.count()).select_from(model).where(model.business_id == business_id)) or 0)


def _write_counts(db_session, business_id: UUID) -> dict[str, int]:
    return {
        "events": _count(db_session, business_id, BusinessEventRow),
        "coverage": _count(db_session, business_id, SourceCoverageRecordRow),
        "audit": _count(db_session, business_id, AuditEventRow),
        "outbox": _count(db_session, business_id, OutboxEventRow),
        "idempotency": _count(db_session, business_id, IdempotencyRecordRow),
    }


def _cursor(occurred_at: datetime) -> str:
    raw = f"{occurred_at.isoformat()}|{UUID(int=1)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
