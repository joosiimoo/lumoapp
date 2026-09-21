from __future__ import annotations

from typing import Any

from app.agent.contracts import LLMProvider
from app.agent.providers.scripted import ScriptedLLMProvider


class FakeLLMProvider(ScriptedLLMProvider):
    """Non-mutating local/test adapter. No repository or database access."""


def inspect_llm_provider_contract(provider: LLMProvider) -> None:
    """Used by tests to assert the port has no persistence parameters."""
    interpret = provider.interpret
    names = set(interpret.__code__.co_varnames[: interpret.__code__.co_argcount])
    forbidden = {"session", "repository", "engine", "connection", "database_url"}
    overlap = names & forbidden
    if overlap:
        raise AssertionError(f"LLMProvider must not accept persistence args: {overlap}")
