from __future__ import annotations

from pydantic import ValidationError

from app.agent.contracts import AgentDecision
from app.agent.generative_ui import GenerativeUIComposer, GenerativeUIContract, GenerativeUIRegistry
from app.agent.orchestrator import FoundationOrchestrator, validate_decision_payload
from app.agent.providers.fake import FakeLLMProvider, inspect_llm_provider_contract
from app.agent.tools import ToolRegistry
from app.application.workflows.outcomes import EmptyOutcomeEngine, OutcomeStatus
from app.policies import PolicyDecisionName, PolicyRequest
from app.policies.engine import SEC_002, FoundationPolicyEngine
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
        PolicyRequest(action="execute_tool", tool_id="sale.commit@1", tool_registered=False, from_llm=True)
    )
    assert decision.decision is PolicyDecisionName.DENY
    assert SEC_002 in decision.rule_ids
    registry = ToolRegistry()
    assert registry.get("sale.commit@1") is None
    assert registry.allowed_ids() == []
    orchestrator = FoundationOrchestrator(
        provider=_ToolHappyProvider(),
        tools=registry,
        policies=engine,
    )
    response = orchestrator.handle("sell")
    assert "not available" in response.text.lower() or "foundation" in response.text.lower()


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
        return AgentDecision(intent="sale.create", candidate_tool="sale.commit@1")
