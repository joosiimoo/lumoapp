from __future__ import annotations

from typing import Any, Protocol


class OutcomeStatus:
    NOT_READY = "not_ready"
    READY = "ready"


class OutcomeEngine(Protocol):
    def evaluate(self, outcome_id: str, confirmed_state: dict[str, Any], model_claim: str | None = None) -> str: ...


class EmptyOutcomeEngine:
    def __init__(self) -> None:
        self._definitions: dict[str, Any] = {}

    def register(self, outcome_id: str, definition: dict[str, Any]) -> None:
        self._definitions[outcome_id] = definition

    def evaluate(self, outcome_id: str, confirmed_state: dict[str, Any], model_claim: str | None = None) -> str:
        _ = (confirmed_state, model_claim)
        if outcome_id not in self._definitions:
            return OutcomeStatus.NOT_READY
        return OutcomeStatus.NOT_READY
