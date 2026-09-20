from __future__ import annotations

from typing import Any

from app.agent.contracts import AgentDecision, AgentResponse, LLMProvider, ProviderStatus


class FakeLLMProvider:
    """Non-mutating test/local adapter. No repository or database access."""

    def interpret(
        self,
        message: str,
        context: dict[str, Any],
        allowed_tools: list[str],
    ) -> AgentDecision:
        _ = (message, context, allowed_tools)
        return AgentDecision(
            intent="unsupported",
            clarification_question="No domain tools are registered in the foundation runtime.",
        )

    def compose(self, result: dict[str, Any], ui_contracts: list[dict[str, Any]]) -> AgentResponse:
        _ = ui_contracts
        text = str(result.get("text") or "Lumo foundation is ready.")
        return AgentResponse(text=text, ui=[])

    def health(self) -> ProviderStatus:
        return ProviderStatus(ready=False, provider="fake", detail="no vendor configured")


def inspect_llm_provider_contract(provider: LLMProvider) -> None:
    """Used by tests to assert the port has no persistence parameters."""
    interpret = provider.interpret
    names = set(interpret.__code__.co_varnames[: interpret.__code__.co_argcount])
    forbidden = {"session", "repository", "engine", "connection", "database_url"}
    overlap = names & forbidden
    if overlap:
        raise AssertionError(f"LLMProvider must not accept persistence args: {overlap}")
