from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from app.domain.catalog.product import SaleUnit
from app.domain.sales.quantity import InputUnit
from app.domain.shared.money import Money


class SaleSessionStatus(StrEnum):
    OPEN = "open"
    READY_TO_CHARGE = "ready_to_charge"


class TotalizeKind(StrEnum):
    TRANSITION = "transition"
    READ_BACK = "read_back"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class SaleSession:
    id: UUID
    business_id: UUID
    actor_id: UUID
    conversation_id: str | None
    status: SaleSessionStatus
    currency: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SaleItem:
    id: UUID
    business_id: UUID
    sale_session_id: UUID
    product_id: UUID
    product_name_snapshot: str
    quantity_input: Decimal
    unit_input: InputUnit
    quantity_normalized: Decimal
    unit_normalized: SaleUnit
    unit_price: Money
    line_total: Money


def can_add_item(status: SaleSessionStatus) -> bool:
    return status is SaleSessionStatus.OPEN


def classify_totalize(status: SaleSessionStatus | None, item_count: int) -> TotalizeKind:
    if status is None or item_count < 1:
        return TotalizeKind.EMPTY
    if status is SaleSessionStatus.READY_TO_CHARGE:
        return TotalizeKind.READ_BACK
    if status is SaleSessionStatus.OPEN:
        return TotalizeKind.TRANSITION
    return TotalizeKind.EMPTY


def sum_session_total(items: list[SaleItem], *, currency: str = "MXN") -> Money:
    if not items:
        return Money("0.00", currency)
    total = items[0].line_total.amount
    code = items[0].line_total.currency
    for item in items[1:]:
        total = total + item.line_total.amount
    return Money(total, code)
