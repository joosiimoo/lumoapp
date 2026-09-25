from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.application.ports import IdentityPort
from app.application.workflows.get_daily_close_preparation import _amount_text
from app.domain.operations import RANKED_TYPES, WorkItem, WorkItemType, business_date_for
from app.domain.operations.business_date import InvalidBusinessTimezone
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.operations import OperationsRepository

NO_PENDING_STEP_TEXT = "No hay un paso pendiente para el cierre de hoy."
REQUEST_CLOSE_ACTION = {"action_id": "closing.request@1"}
_TWO_PLACES = Decimal("0.01")


class GetNextBestAction:
    def __init__(self, *, identities: IdentityPort, operations: OperationsRepository) -> None:
        self._identities = identities
        self._operations = operations

    def execute(self, *, tenant: TenantContext, now: datetime | None = None) -> dict[str, Any]:
        business = self._identities.get_business(tenant)
        instant = now if now is not None else utcnow()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValidationAppError("clock must be timezone-aware UTC")
        instant = instant.astimezone(UTC)
        try:
            business_date = business_date_for(instant, business.timezone)
        except InvalidBusinessTimezone as exc:
            raise ValidationAppError("invalid business timezone") from exc
        day = self._operations.get_by_date(tenant=tenant, business_date=business_date)
        if day is None:
            return {
                "operational_day_id": None,
                "day_status": None,
                "pending_count": 0,
                "next_best_action": None,
            }
        open_rows = self._operations.list_open_work_items(tenant=tenant, operational_day_id=day.id)
        chosen = _best(open_rows)
        return {
            "operational_day_id": str(day.id),
            "day_status": day.status.value,
            "pending_count": len(open_rows),
            "next_best_action": None if chosen is None else project_work_item(chosen),
        }


def project_work_item(item: WorkItem) -> dict[str, Any]:
    evidence = dict(item.evidence)
    copy = _copy(item.type, evidence)
    actions = [] if item.type is WorkItemType.CASH_COUNT_REQUIRED else [dict(REQUEST_CLOSE_ACTION)]
    risk, reversible = _risk(item.type)
    return {
        "work_item_id": str(item.id),
        "operational_day_id": str(item.operational_day_id),
        "outcome_type": "daily_close_ready",
        "type": item.type.value,
        "title": copy["title"],
        "reason": copy["reason"],
        "expected_result": copy["expected_result"],
        "priority": item.priority.value,
        "responsible_party": item.responsible_party,
        "evidence": evidence,
        "risk": risk,
        "reversible": reversible,
        "expires_at": None,
        "status": "open",
        "actions": actions,
    }


def fallback_text_for(action: dict[str, Any]) -> str:
    return f"{action['title']} {action['reason']}"


def _best(rows: list[WorkItem]) -> WorkItem | None:
    if not rows:
        return None
    order = {item_type: index for index, item_type in enumerate(RANKED_TYPES)}
    return min(rows, key=lambda row: order[row.type])


def _risk(item_type: WorkItemType) -> tuple[str, bool]:
    if item_type is WorkItemType.CASH_COUNT_REQUIRED:
        return "blocks_close", True
    if item_type is WorkItemType.CASH_DIFFERENCE_REVIEW:
        return "visible_difference", True
    return "requires_confirmation", False


def _copy(item_type: WorkItemType, evidence: dict[str, Any]) -> dict[str, str]:
    expected = _amount_text({"amount": str(evidence["expected_cash"])})
    if item_type is WorkItemType.CASH_COUNT_REQUIRED:
        return {
            "title": "Cuenta el efectivo para continuar con el cierre.",
            "reason": f"Esperamos {expected} en efectivo y todavía no hay un conteo.",
            "expected_result": "Un conteo de efectivo queda registrado para esta jornada.",
        }
    if item_type is WorkItemType.CASH_DIFFERENCE_REVIEW:
        counted = _amount_text({"amount": str(evidence["counted_cash"])})
        absolute = _amount_text({"amount": _absolute(str(evidence["cash_difference"]))})
        if evidence.get("cash_status") == "over":
            title = f"Hay un sobrante de {absolute}. Revisa la diferencia antes de confirmar el cierre."
        else:
            title = f"Hay un faltante de {absolute}. Revisa la diferencia antes de confirmar el cierre."
        return {
            "title": title,
            "reason": (
                f"El conteo es {counted} y las ventas registradas en Lumo esperan {expected} en efectivo."
            ),
            "expected_result": "Puedes volver a contar o confirmar el cierre con esta diferencia visible.",
        }
    return {
        "title": "La caja está cuadrada. El siguiente paso es cerrar la jornada.",
        "reason": (
            f"El efectivo contado coincide con los {expected} esperados de las ventas registradas en Lumo."
        ),
        "expected_result": "La jornada queda cerrada.",
    }


def _absolute(signed: str) -> str:
    amount = abs(Decimal(signed)).quantize(_TWO_PLACES)
    return format(amount, "f")
