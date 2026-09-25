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

    def registered_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def evaluate(self, outcome_id: str, confirmed_state: dict[str, Any], model_claim: str | None = None) -> str:
        _ = model_claim
        definition = self._definitions.get(outcome_id)
        if definition is None:
            return OutcomeStatus.NOT_READY
        evaluator = definition.get("gate_evaluator")
        if evaluator is None:
            return OutcomeStatus.NOT_READY
        from app.domain.operations.daily_close_outcome import OutcomeVerdict
        from app.domain.shared.errors import ValidationAppError

        verdict = evaluator(confirmed_state)
        if not isinstance(verdict, OutcomeVerdict):
            raise ValidationAppError("registered outcome has no persisted verdict for this state")
        return verdict.status.value
