from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import ValidationError

from app.agent.contracts import AgentDecision, AgentResponse, LLMProvider
from app.agent.tools import ToolRegistry
from app.policies import PolicyEngine, PolicyRequest


class LumoOrchestrator(Protocol):
    def handle(self, message: str, context: dict[str, Any] | None = None) -> AgentResponse: ...


@dataclass
class FoundationOrchestrator:
    provider: LLMProvider
    tools: ToolRegistry
    policies: PolicyEngine

    def handle(self, message: str, context: dict[str, Any] | None = None) -> AgentResponse:
        context = context or {}
        raw = self.provider.interpret(message, context, self.tools.allowed_ids())
        try:
            payload = raw.model_dump() if hasattr(raw, "model_dump") else raw
            decision = AgentDecision.model_validate(payload)
        except (ValidationError, AttributeError, TypeError):
            return AgentResponse(text="I could not interpret that safely.", ui=[])
        if decision.candidate_tool:
            registered = self.tools.is_registered(decision.candidate_tool)
            policy = self.policies.evaluate(
                PolicyRequest(
                    action="execute_tool",
                    tool_id=decision.candidate_tool,
                    tool_registered=registered,
                    from_llm=True,
                )
            )
            if not registered or policy.decision.value == "deny":
                return AgentResponse(
                    text=decision.clarification_question
                    or "That action is not available.",
                    ui=[],
                )
        result = {
            "text": decision.clarification_question or "Lumo foundation received the message.",
            "intent": decision.intent,
        }
        return self.provider.compose(result, [])


def validate_decision_payload(payload: Any) -> AgentDecision:
    return AgentDecision.model_validate(payload)
