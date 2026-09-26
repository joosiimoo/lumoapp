from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.agent.contracts import AgentDecision
from app.agent.providers.scripted import ScriptedLLMProvider
from app.application.workflows.get_daily_close_preparation import build_close_preparation
from app.domain.operations import (
    CashCount,
    CashCountSource,
    CashStatus,
    cash_difference,
    cash_status_for,
    parse_counted_amount,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.policies import PolicyRequest
from app.policies.engine import CLOSE_001, CLOSE_002, SEC_002, FoundationPolicyEngine


def _count(amount: str, counted_at: datetime | None = None) -> CashCount:
    return CashCount(
        id=new_uuid7(),
        business_id=new_uuid7(),
        operational_day_id=new_uuid7(),
        actor_id=new_uuid7(),
        amount=Decimal(amount),
        currency="MXN",
        source=CashCountSource.MANUAL_CAPTURE,
        counted_at=counted_at or datetime(2026, 9, 21, 23, 10, tzinfo=UTC),
    )


def test_parse_counted_amount_accepts_closed_shapes() -> None:
    assert parse_counted_amount("120") == Decimal("120.00")
    assert parse_counted_amount("22.50") == Decimal("22.50")
    assert parse_counted_amount("22,50") == Decimal("22.50")
    assert parse_counted_amount("$22.5") == Decimal("22.50")
    assert parse_counted_amount("0") == Decimal("0.00")


@pytest.mark.parametrize("raw", ["-1", "1.005", "abc", "", " ", "1,200", "1.2.3", "12e2", None, True])
def test_parse_counted_amount_rejects_everything_else(raw) -> None:
    with pytest.raises(ValidationAppError):
        parse_counted_amount(raw)


def test_parse_counted_amount_rejects_float() -> None:
    with pytest.raises(TypeError):
        parse_counted_amount(20.5)


def test_difference_and_status_are_signed_and_derived() -> None:
    assert cash_difference("22.50", Decimal("20.00")) == Decimal("-2.50")
    assert cash_difference("22.50", Decimal("25.00")) == Decimal("2.50")
    assert cash_difference("22.50", Decimal("22.50")) == Decimal("0.00")
    assert cash_difference("22.50", None) is None
    assert cash_status_for(Decimal("-2.50")) is CashStatus.SHORT
    assert cash_status_for(Decimal("2.50")) is CashStatus.OVER
    assert cash_status_for(Decimal("0.00")) is CashStatus.BALANCED
    assert cash_status_for(None) is CashStatus.NOT_COUNTED


def test_difference_rejects_float() -> None:
    with pytest.raises(TypeError):
        cash_difference(22.5, Decimal("20.00"))


def test_fallback_text_shortage_and_not_counted() -> None:
    from datetime import date

    from app.domain.operations import OperationalDay, OperationalDayStatus

    day = OperationalDay(
        id=new_uuid7(),
        business_id=new_uuid7(),
        business_date=date(2026, 9, 21),
        status=OperationalDayStatus.OPEN,
        timezone="America/Mexico_City",
    )
    short = build_close_preparation(
        business_date=date(2026, 9, 21),
        currency="MXN",
        day=day,
        sale_count=3,
        expected_cash="22.50",
        count=_count("20.00"),
    )
    assert short["cash_status"] == "short"
    assert short["cash_difference"] == {"amount": "-2.50", "currency": "MXN"}
    assert short["text"] == (
        "Cierre 2026-09-21 · Efectivo esperado $22.50 · Contado $20.00 · Diferencia -$2.50 · Faltante"
    )
    over = build_close_preparation(
        business_date=date(2026, 9, 21),
        currency="MXN",
        day=day,
        sale_count=3,
        expected_cash="22.50",
        count=_count("25.00"),
    )
    assert over["text"].endswith("Diferencia $2.50 · Sobrante")
    balanced = build_close_preparation(
        business_date=date(2026, 9, 21),
        currency="MXN",
        day=day,
        sale_count=3,
        expected_cash="22.50",
        count=_count("22.50"),
    )
    assert balanced["text"].endswith("Diferencia $0.00 · Caja cuadrada")
    not_counted = build_close_preparation(
        business_date=date(2026, 9, 21),
        currency="MXN",
        day=day,
        sale_count=3,
        expected_cash="22.50",
        count=None,
    )
    assert not_counted["cash_status"] == "not_counted"
    assert not_counted["counted_cash"] is None
    assert not_counted["cash_difference"] is None
    assert not_counted["counted_at"] is None
    assert not_counted["cash_count_id"] is None
    assert not_counted["text"] == "Cierre 2026-09-21 · Efectivo esperado $22.50 · Falta contar efectivo"
    assert "0.00" not in not_counted["text"].split("esperado")[1]


def test_closed_cash_count_phrases() -> None:
    provider = ScriptedLLMProvider()
    for phrase in ("tengo 120 en caja", "hay 120 en caja", "conté 120", "caja 120", "Tengo 120 en caja"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "record_cash_count", phrase
        assert decision.candidate_tool == "closing.submit_cash_count@1"
        assert decision.counted_amount == "120"
    assert provider.interpret("conté 22,50", {}, []).counted_amount == "22.50"
    assert provider.interpret("conté 22.50", {}, []).counted_amount == "22.50"
    assert provider.interpret("tengo $20 en caja", {}, []).counted_amount == "20"


def test_unsupported_cash_wording_clarifies() -> None:
    provider = ScriptedLLMProvider()
    for phrase in ("tengo 1,200 en caja", "cuánto falta en caja la semana pasada", "caja"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "unsupported", phrase
        assert decision.candidate_tool is None
        assert decision.counted_amount is None
    bare = provider.interpret("120", {}, [])
    assert bare.intent != "record_cash_count"
    assert bare.counted_amount is None


def test_closed_preparation_phrases_and_no_close_guard() -> None:
    provider = ScriptedLLMProvider()
    for phrase in (
        "preparar el cierre",
        "preparar cierre",
        "cuanto deberia haber en caja",
        "¿Cuánto debería haber en caja?",
        "efectivo esperado",
    ):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "close_preparation", phrase
        assert decision.candidate_tool == "closing.prepare@1"
    for phrase in ("cerrar el día", "cerrar la jornada", "cerrar caja"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "request_close", phrase
        assert decision.candidate_tool == "closing.prepare@1"
    for phrase in ("confirmar cierre", "sí, cerrar", "confirmar"):
        decision = provider.interpret(phrase, {}, [])
        assert decision.intent == "confirm_close", phrase
        assert decision.candidate_tool == "closing.confirm@1"


def test_sale_utterances_keep_their_path() -> None:
    decision = ScriptedLLMProvider().interpret("900gr zanahoria", {}, [])
    assert decision.intent == "add_sale_item"
    assert decision.candidate_tool == "sale.add_item@1"
    assert decision.counted_amount is None


@pytest.mark.parametrize("amount", ["-5", "1.005", "abc", "", "1,200"])
def test_invalid_counted_amount_is_discarded_by_the_contract(amount: str) -> None:
    with pytest.raises(Exception):
        AgentDecision(intent="record_cash_count", counted_amount=amount)


class _Business:
    def __init__(self, timezone: str = "America/Mexico_City", currency: str = "MXN") -> None:
        self.timezone = timezone
        self.currency = currency


class _Identities:
    def __init__(self, business: _Business) -> None:
        self._business = business

    def get_business(self, tenant):  # noqa: ANN001
        return self._business


class _SpyIdempotency:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def peek(self, **_kwargs):
        self.calls.append("peek")
        return None

    def begin(self, **_kwargs):
        self.calls.append("begin")
        return None

    def complete(self, **_kwargs) -> None:
        self.calls.append("complete")


class _SpyOperations:
    def __init__(self, current: CashCount | None, day) -> None:  # noqa: ANN001
        self.current = current
        self.day = day
        self.calls: list[str] = []
        self.work_items: list = []
        self.outcome = None

    def get_snapshot_for_day(self, **_kwargs):
        return None

    def get_daily_close_outcome(self, **_kwargs):
        return self.outcome

    def insert_daily_close_outcome(self, *, tenant, outcome):  # noqa: ANN001
        self.calls.append("insert_outcome")
        self.outcome = outcome
        return outcome

    def update_daily_close_outcome_evidence(self, *, tenant, outcome_run_id, evidence, updated_at):  # noqa: ANN001
        self.calls.append("update_outcome_evidence")
        return self.outcome

    def update_daily_close_outcome_status(self, **_kwargs):
        self.calls.append("update_outcome_status")
        return self.outcome

    def link_null_work_items(self, **_kwargs) -> int:
        self.calls.append("link_work_items")
        return 0

    def lock_day_for_update(self, **_kwargs):
        self.calls.append("lock")
        return self.day

    def expected_cash(self, **_kwargs) -> str:
        self.calls.append("expected_cash")
        return "20.00"

    def summarize_day(self, **_kwargs):
        from app.domain.operations import DaySummaryTotals

        return DaySummaryTotals(
            sale_count=1,
            gross_sales_total="20.00",
            cash_total="20.00",
            card_total="0.00",
            transfer_total="0.00",
            currency="MXN",
        )

    def get_current_cash_count(self, **_kwargs):
        self.calls.append("get_current")
        return self.current

    def mark_superseded(self, **_kwargs) -> None:
        self.calls.append("mark_superseded")

    def insert_cash_count(self, *, tenant, cash_count):  # noqa: ANN001
        self.calls.append("insert")
        self.current = cash_count
        return cash_count

    def insert_source_coverage_if_absent(self, *, tenant, record):  # noqa: ANN001
        self.calls.append("insert_source_coverage")
        return record

    def append_business_event(self, *, tenant, event):  # noqa: ANN001
        self.calls.append("append_business_event")
        return event

    def list_open_work_items(self, **_kwargs):
        self.calls.append("list_open_work_items")
        return [item for item in self.work_items if item.status.value == "open"]

    def insert_work_item(self, *, tenant, work_item):  # noqa: ANN001
        self.calls.append("insert_work_item")
        self.work_items.append(work_item)
        return work_item

    def refresh_work_item_evidence(self, *, tenant, work_item_id, reason_code, evidence, updated_at):  # noqa: ANN001
        self.calls.append("refresh_work_item_evidence")
        return next(item for item in self.work_items if item.id == work_item_id)

    def resolve_work_item(self, **_kwargs):
        self.calls.append("resolve_work_item")
        raise AssertionError("cash count unit fixtures have no open work item to resolve")


class _SpyAudit:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


class _SpyOutbox:
    def __init__(self) -> None:
        self.events: list[str] = []

    def enqueue(self, *, tenant, event_type, payload) -> None:  # noqa: ANN001
        self.events.append(event_type)


def _workflow(*, current: CashCount | None, business: _Business | None = None):
    from datetime import date

    from app.application.workflows.record_cash_count import RecordCashCount
    from app.domain.operations import OperationalDay, OperationalDayStatus

    business = business or _Business()
    day = OperationalDay(
        id=new_uuid7(),
        business_id=new_uuid7(),
        business_date=date(2026, 9, 21),
        status=OperationalDayStatus.OPEN,
        timezone=business.timezone,
    )
    idempotency = _SpyIdempotency()
    operations = _SpyOperations(current, day)
    audit = _SpyAudit()
    outbox = _SpyOutbox()
    workflow = RecordCashCount(
        identities=_Identities(business),
        operations=operations,
        audit=audit,
        idempotency=idempotency,
        outbox=outbox,
    )
    return workflow, idempotency, operations, audit, outbox


def _execute(workflow, amount: str):
    from app.domain.shared.tenant import TenantContext

    return workflow.execute(
        tenant=TenantContext(business_id=new_uuid7(), actor_id=new_uuid7()),
        conversation_id="conv-unit",
        counted_amount=amount,
        idempotency_key="unit-key",
        correlation_id="unit-correlation",
        raw_message=f"tengo {amount} en caja",
        counted_at=datetime(2026, 9, 21, 23, 10, tzinfo=UTC),
    )


def test_equal_amount_read_back_never_reserves_the_key() -> None:
    workflow, idempotency, operations, audit, outbox = _workflow(current=_count("20.00"))
    result = _execute(workflow, "20.00")
    assert result.kind == "read_back"
    assert idempotency.calls == ["peek"]
    assert "begin" not in idempotency.calls
    assert "insert" not in operations.calls
    assert "mark_superseded" not in operations.calls
    assert audit.records == []
    assert outbox.events == []


def test_recount_reserves_the_key_and_updates_before_inserting() -> None:
    workflow, idempotency, operations, audit, outbox = _workflow(current=_count("20.00"))
    result = _execute(workflow, "22.50")
    assert result.kind == "committed"
    assert idempotency.calls == ["peek", "begin", "complete"]
    assert operations.calls.index("mark_superseded") < operations.calls.index("insert")
    assert [record["action"] for record in audit.records] == [
        "closing.submit_cash_count@1",
        "outcome_run.created",
        "work_item.created",
    ]
    assert outbox.events == ["cash_count.recorded"]


def test_first_count_inserts_without_superseding() -> None:
    workflow, idempotency, operations, audit, outbox = _workflow(current=None)
    result = _execute(workflow, "20.00")
    assert result.kind == "committed"
    assert "mark_superseded" not in operations.calls
    assert operations.calls.count("insert") == 1
    assert idempotency.calls == ["peek", "begin", "complete"]
    assert audit.records[0]["before_payload"] is None
    assert outbox.events == ["cash_count.recorded"]


def test_invalid_business_timezone_raises_so_the_request_rolls_back() -> None:
    workflow, _idempotency, _operations, _audit, _outbox = _workflow(
        current=None,
        business=_Business(timezone="Not/AZone"),
    )
    with pytest.raises(ValidationAppError):
        _execute(workflow, "20.00")


def test_close_policies() -> None:
    engine = FoundationPolicyEngine()
    allow = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.submit_cash_count@1",
            tool_registered=True,
            from_llm=True,
            arguments={"counted_amount": "20.00"},
        )
    )
    assert allow.decision.value == "allow"
    assert CLOSE_001 in allow.rule_ids
    clarify = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.submit_cash_count@1",
            tool_registered=True,
            from_llm=True,
            arguments={"day_exists": False},
        )
    )
    assert clarify.decision.value == "clarify"
    assert clarify.reason_code == "operational_day_not_started"
    read = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.prepare@1",
            tool_registered=True,
            from_llm=True,
            arguments={},
        )
    )
    assert read.decision.value == "allow"
    assert CLOSE_002 in read.rule_ids
    for tool_id in ("closing.confirm@1", "closing.reopen@1"):
        denied = engine.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id=tool_id,
                tool_registered=False,
                from_llm=True,
                arguments={},
            )
        )
        assert denied.decision.value == "deny"
        assert SEC_002 in denied.rule_ids
    for arguments in (
        {"expected_cash": "22.50"},
        {"cash_difference": "-2.50"},
        {"counted_cash": "20.00"},
        {"cash_status": "short"},
        {"operational_day_id": str(new_uuid7())},
        {"business_date": "2026-09-21"},
    ):
        spoofed = engine.evaluate(
            PolicyRequest(
                action="execute_tool",
                tool_id="closing.submit_cash_count@1",
                tool_registered=True,
                from_llm=True,
                arguments=arguments,
            )
        )
        assert spoofed.decision.value == "deny"
        assert spoofed.reason_code == "model_supplied_cash_values"
    invalid = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="closing.submit_cash_count@1",
            tool_registered=True,
            from_llm=True,
            arguments={"counted_amount": "1.005"},
        )
    )
    assert invalid.decision.value == "deny"
    assert invalid.reason_code == "counted_amount_invalid"
