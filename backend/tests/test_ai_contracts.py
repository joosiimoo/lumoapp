from __future__ import annotations

from pydantic import ValidationError

from app.agent.contracts import AgentDecision
from app.agent.generative_ui import GenerativeUIComposer, GenerativeUIContract, GenerativeUIRegistry
from app.agent.orchestrator import FoundationOrchestrator, validate_decision_payload
from app.agent.providers.fake import FakeLLMProvider, inspect_llm_provider_contract
from app.agent.providers.scripted import ScriptedLLMProvider
from app.agent.tools import ToolRegistry
from app.application.workflows.outcomes import EmptyOutcomeEngine, OutcomeStatus
from app.policies import PolicyDecisionName, PolicyRequest
from app.policies.engine import PAY_001, SALE_002, SALE_003, SALE_004, SEC_002, FoundationPolicyEngine
import inspect

from app.agent.contracts import LLMProvider


def test_fake_provider_has_no_persistence_hooks() -> None:
    provider = FakeLLMProvider()
    inspect_llm_provider_contract(provider)
    signature = inspect.signature(LLMProvider.interpret)
    for name in signature.parameters:
        assert name not in {"session", "repository", "engine", "connection", "database_url"}
    status = provider.health()
    assert status.ready is False
    assert status.provider == "fake"


def test_invalid_agent_decision_is_discarded() -> None:
    try:
        validate_decision_payload({"intent": "", "candidate_tool": "sale.commit@1"})
        raise AssertionError("expected validation error")
    except ValidationError:
        pass
    orchestrator = FoundationOrchestrator(
        provider=_BrokenProvider(),
        tools=ToolRegistry(),
        policies=FoundationPolicyEngine(),
    )
    response = orchestrator.handle("385 tarjeta")
    assert response.ui == []
    assert "safely" in response.text.lower() or "interpret" in response.text.lower()


def test_unregistered_tool_is_denied() -> None:
    engine = FoundationPolicyEngine()
    decision = engine.evaluate(
        PolicyRequest(action="execute_tool", tool_id="closing.confirm@1", tool_registered=False, from_llm=True)
    )
    assert decision.decision is PolicyDecisionName.DENY
    assert SEC_002 in decision.rule_ids
    registry = ToolRegistry()
    assert registry.get("closing.confirm@1") is None
    assert registry.allowed_ids() == []
    orchestrator = FoundationOrchestrator(
        provider=_ToolHappyProvider(),
        tools=registry,
        policies=engine,
    )
    response = orchestrator.handle("sell")
    assert "not available" in response.text.lower() or "foundation" in response.text.lower() or "catálogo" in response.text.lower()


def test_unknown_outcome_is_not_ready() -> None:
    engine = EmptyOutcomeEngine()
    status = engine.evaluate(
        "daily_close_ready@1",
        {"sales": 1},
        model_claim="the outcome is complete",
    )
    assert status == OutcomeStatus.NOT_READY


def test_composer_refuses_unregistered_component() -> None:
    composer = GenerativeUIComposer(GenerativeUIRegistry())
    try:
        composer.compose(
            GenerativeUIContract(
                component="sale_confirmed_card",
                version=1,
                fallback_text="Venta registrada",
            )
        )
        raise AssertionError("expected unregistered component to fail")
    except Exception as exc:
        assert "unregistered" in str(exc).lower() or "generative" in str(exc).lower()


class _BrokenProvider(FakeLLMProvider):
    def interpret(self, message, context, allowed_tools):  # type: ignore[no-untyped-def]
        return {"intent": ""}


class _ToolHappyProvider(FakeLLMProvider):
    def interpret(self, message, context, allowed_tools):  # type: ignore[no-untyped-def]
        return AgentDecision(intent="sale.create", candidate_tool="closing.confirm@1")


def test_sale_002_denies_add_item_when_ready_to_charge() -> None:
    engine = FoundationPolicyEngine()
    decision = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.add_item@1",
            tool_registered=True,
            arguments={"session_status": "ready_to_charge", "quantity": "1"},
        )
    )
    assert decision.decision is PolicyDecisionName.DENY
    assert SALE_002 in decision.rule_ids


def test_sale_003_blocks_empty_and_allows_ready_read_back() -> None:
    engine = FoundationPolicyEngine()
    empty = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.totalize@1",
            tool_registered=True,
            arguments={"session_status": "open", "item_count": 0},
        )
    )
    assert empty.decision is PolicyDecisionName.DENY
    assert SALE_003 in empty.rule_ids
    ready = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.totalize@1",
            tool_registered=True,
            arguments={"session_status": "ready_to_charge", "item_count": 2},
        )
    )
    assert ready.decision is PolicyDecisionName.ALLOW
    assert SALE_003 in ready.rule_ids
    transition = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.totalize@1",
            tool_registered=True,
            arguments={"session_status": "open", "item_count": 2},
        )
    )
    assert transition.decision is PolicyDecisionName.ALLOW
    assert SALE_003 in transition.rule_ids


def test_sale_004_and_pay_001() -> None:
    engine = FoundationPolicyEngine()
    open_sale = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.commit@1",
            tool_registered=True,
            arguments={"session_status": "open", "payment_method": "cash"},
        )
    )
    assert open_sale.decision is PolicyDecisionName.DENY
    assert SALE_004 in open_sale.rule_ids
    missing_method = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.commit@1",
            tool_registered=True,
            arguments={"session_status": "ready_to_charge"},
        )
    )
    assert missing_method.decision is PolicyDecisionName.CLARIFY
    assert PAY_001 in missing_method.rule_ids
    ready = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.commit@1",
            tool_registered=True,
            arguments={"session_status": "ready_to_charge", "payment_method": "card"},
        )
    )
    assert ready.decision is PolicyDecisionName.ALLOW
    assert SALE_004 in ready.rule_ids
    assert PAY_001 in ready.rule_ids
    confirmed = engine.evaluate(
        PolicyRequest(
            action="execute_tool",
            tool_id="sale.commit@1",
            tool_registered=True,
            arguments={"session_status": "confirmed", "payment_method": "cash"},
        )
    )
    assert confirmed.decision is PolicyDecisionName.ALLOW
    assert SALE_004 in confirmed.rule_ids


def test_scripted_interpreter_totalize_synonyms_and_missing_unit() -> None:
    provider = ScriptedLLMProvider()
    for message in ("totalizar", "TOTAL", " El total "):
        decision = provider.interpret(message, {}, ["sale.totalize@1"])
        assert decision.intent == "totalize_sale"
        assert decision.candidate_tool == "sale.totalize@1"
    cobrar = provider.interpret("cobrar", {}, ["sale.totalize@1", "sale.commit@1"])
    pagar = provider.interpret("pagar", {}, ["sale.totalize@1", "sale.commit@1"])
    assert cobrar.intent != "totalize_sale"
    assert pagar.intent != "totalize_sale"
    assert cobrar.intent != "commit_sale"
    assert pagar.intent != "commit_sale"
    assert pagar.clarification_question is not None
    assert "efectivo" in pagar.clarification_question.lower()
    cash = provider.interpret("pagar en efectivo", {}, ["sale.commit@1"])
    assert cash.intent == "commit_sale"
    assert cash.payment_method == "cash"
    assert cash.candidate_tool == "sale.commit@1"
    card = provider.interpret("con tarjeta", {}, ["sale.commit@1"])
    assert card.intent == "commit_sale"
    assert card.payment_method == "card"
    transfer = provider.interpret("por transferencia", {}, ["sale.commit@1"])
    assert transfer.intent == "commit_sale"
    assert transfer.payment_method == "transfer"
    cheque = provider.interpret("cheque", {}, ["sale.commit@1"])
    assert cheque.intent != "commit_sale"
    mixed = provider.interpret("efectivo y tarjeta", {}, ["sale.commit@1"])
    assert mixed.intent != "commit_sale"
    combined = provider.interpret("900gr zanahoria efectivo", {}, ["sale.commit@1", "sale.add_item@1"])
    assert combined.intent != "commit_sale"
    missing = provider.interpret("2 galletas A", {}, ["sale.add_item@1"])
    assert missing.intent == "add_sale_item"
    assert missing.unit is None
    assert "unit" in missing.missing_fields
    assert missing.product_query == "galletas A"
