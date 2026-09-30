"""Server-owned Business Stream projection for today's operational responsibility.

Pure selector and scripted copy. No I/O, no model call, and no second rank table.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.operations.day import OperationalDayStatus
from app.domain.operations.work_item import WorkItemType

NO_ACTIVE_DAY_RESPONSIBILITY = "Cuando empiece la actividad, organizo el día."
ORGANIZING_RESPONSIBILITY = "Lumo está organizando el cierre"
ORGANIZING_DETAIL = "Con lo registrado hasta ahora."
CASH_COUNT_RESPONSIBILITY = "Necesito que registres el efectivo contado"
CASH_COUNT_WHY = "Hace falta para continuar con el cierre."
CASH_DIFFERENCE_RESPONSIBILITY = "Esperando tu revisión"
CASH_DIFFERENCE_WHY = "La diferencia queda visible. No indica por qué ocurrió."
READY_RESPONSIBILITY = "Cierre listo para confirmar"
READY_DETAIL = "Puedes revisarlo y confirmar el cierre."
READY_WHY = "El cierre está listo para tu confirmación."
CLOSED_RESPONSIBILITY = "Cierre completado"
UNAVAILABLE_RESPONSIBILITY = "No pude consultar el estado de hoy."
COVERAGE_SENTENCE = "Este cierre considera las operaciones registradas en Lumo."
COVERAGE_LIMITATION = "only_lumo_registered_operations"
REQUEST_CLOSE_MESSAGE = "cerrar el día"

_FORBIDDEN_COPY = (
    "día completo",
    "todas las ventas",
    "no hubo más operaciones",
    "no ocurrieron más operaciones",
    "workitem",
    "outcomerun",
    "business stream",
    "source coverage",
)


class OperatorState(StrEnum):
    NO_ACTIVE_DAY = "no_active_day"
    ORGANIZING = "organizing"
    CASH_COUNT_REQUIRED = "cash_count_required"
    CASH_DIFFERENCE = "cash_difference"
    READY_TO_CLOSE = "ready_to_close"
    CLOSED = "closed"
    UNAVAILABLE = "unavailable"


class CloseProgress(StrEnum):
    NONE = "none"
    PROGRESSING = "progressing"
    WAITING = "waiting"
    READY = "ready"
    COMPLETED = "completed"


@dataclass(frozen=True, slots=True)
class StreamCopy:
    responsibility: str
    detail: str | None
    why: str | None


def select_business_stream_state(
    *,
    day_status: OperationalDayStatus | None,
    desired_type: WorkItemType | None,
    has_snapshot: bool,
) -> tuple[OperatorState, CloseProgress | None]:
    """Map live day facts onto the closed operator surface. OutcomeRun is not an input."""
    if day_status is None:
        return OperatorState.NO_ACTIVE_DAY, CloseProgress.NONE
    if day_status is OperationalDayStatus.CLOSED:
        if not has_snapshot:
            return OperatorState.UNAVAILABLE, None
        return OperatorState.CLOSED, CloseProgress.COMPLETED
    if desired_type is WorkItemType.CASH_COUNT_REQUIRED:
        return OperatorState.CASH_COUNT_REQUIRED, CloseProgress.WAITING
    if desired_type is WorkItemType.CASH_DIFFERENCE_REVIEW:
        return OperatorState.CASH_DIFFERENCE, CloseProgress.WAITING
    if desired_type is WorkItemType.CLOSE_CONFIRMATION_REQUIRED:
        return OperatorState.READY_TO_CLOSE, CloseProgress.READY
    return OperatorState.ORGANIZING, CloseProgress.PROGRESSING


def scripted_copy(*, state: OperatorState, expected_cash_text: str | None) -> StreamCopy:
    if state is OperatorState.NO_ACTIVE_DAY:
        copy = StreamCopy(NO_ACTIVE_DAY_RESPONSIBILITY, None, None)
    elif state is OperatorState.ORGANIZING:
        copy = StreamCopy(ORGANIZING_RESPONSIBILITY, ORGANIZING_DETAIL, None)
    elif state is OperatorState.CASH_COUNT_REQUIRED:
        if expected_cash_text is None:
            raise ValueError("cash count copy requires the server expected cash")
        copy = StreamCopy(
            CASH_COUNT_RESPONSIBILITY,
            f"Espero {expected_cash_text} en caja. Cuando termines, registra cuánto tienes para continuar con el cierre.",
            CASH_COUNT_WHY,
        )
    elif state is OperatorState.CASH_DIFFERENCE:
        copy = StreamCopy(CASH_DIFFERENCE_RESPONSIBILITY, None, CASH_DIFFERENCE_WHY)
    elif state is OperatorState.READY_TO_CLOSE:
        copy = StreamCopy(READY_RESPONSIBILITY, READY_DETAIL, READY_WHY)
    elif state is OperatorState.CLOSED:
        copy = StreamCopy(CLOSED_RESPONSIBILITY, None, None)
    else:
        copy = StreamCopy(UNAVAILABLE_RESPONSIBILITY, None, None)
    assert_merchant_copy(copy.responsibility, copy.detail, copy.why)
    return copy


def primary_action(
    *,
    state: OperatorState,
    work_item_id: UUID | None,
    outcome_run_id: UUID | None,
) -> dict[str, Any] | None:
    """At most one action. The panel does not carry closing.request@1 or a confirmation token."""
    if state in {
        OperatorState.CASH_COUNT_REQUIRED,
        OperatorState.CASH_DIFFERENCE,
        OperatorState.READY_TO_CLOSE,
    }:
        return {
            "kind": "prepare_daily_close",
            "label": "Preparar el cierre del día",
            "invocation": "close_workspace",
            "message": None,
            "action_id": None,
            "work_item_id": _id(work_item_id),
            "outcome_run_id": _id(outcome_run_id),
        }
    return None


def coverage_claim() -> dict[str, str]:
    claim = {"sentence": COVERAGE_SENTENCE, "limitation_code": COVERAGE_LIMITATION}
    assert_merchant_copy(claim["sentence"])
    return claim


def assert_merchant_copy(*parts: str | None) -> None:
    text = " ".join(part for part in parts if part).casefold()
    for phrase in _FORBIDDEN_COPY:
        if phrase in text:
            raise ValueError(f"merchant copy must not say {phrase}")


def _id(value: UUID | None) -> str | None:
    return None if value is None else str(value)
