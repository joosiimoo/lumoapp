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
    CONFIRMED = "confirmed"


class PaymentMethod(StrEnum):
    CASH = "cash"
    CARD = "card"
    TRANSFER = "transfer"


class PaymentStatus(StrEnum):
    RECORDED = "recorded"


class PaymentSource(StrEnum):
    MANUAL_CAPTURE = "manual_capture"


class TotalizeKind(StrEnum):
    TRANSITION = "transition"
    READ_BACK = "read_back"
    EMPTY = "empty"


class CommitKind(StrEnum):
    TRANSITION = "transition"
    READ_BACK = "read_back"
    NOT_READY = "not_ready"
    NOT_FOUND = "not_found"


PAYMENT_METHOD_LABELS = {
    PaymentMethod.CASH: "Efectivo",
    PaymentMethod.CARD: "Tarjeta",
    PaymentMethod.TRANSFER: "Transferencia",
}


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
    operational_day_id: UUID | None = None
    confirmed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Payment:
    id: UUID
    business_id: UUID
    sale_session_id: UUID
    actor_id: UUID
    method: PaymentMethod
    amount: Money
    status: PaymentStatus = PaymentStatus.RECORDED
    source: PaymentSource = PaymentSource.MANUAL_CAPTURE
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SaleItemSource(StrEnum):
    CATALOG = "catalog"
    FREE_CONCEPT = "free_concept"


@dataclass(frozen=True, slots=True)
class SaleItem:
    id: UUID
    business_id: UUID
    sale_session_id: UUID
    product_id: UUID | None
    product_name_snapshot: str
    quantity_input: Decimal
    unit_input: InputUnit
    quantity_normalized: Decimal
    unit_normalized: SaleUnit
    unit_price: Money
    line_total: Money
    source_type: SaleItemSource = SaleItemSource.CATALOG

    def __post_init__(self) -> None:
        from app.domain.shared.errors import ValidationAppError

        if self.source_type is SaleItemSource.CATALOG:
            if self.product_id is None:
                raise ValidationAppError("a catalog sale item requires a product")
            return
        if self.product_id is not None:
            raise ValidationAppError("a free concept cannot reference a product")
        if not self.product_name_snapshot.strip():
            raise ValidationAppError("a free concept requires a name")
        if self.line_total.amount <= 0 or self.unit_price.amount <= 0:
            raise ValidationAppError("price must be greater than zero")


def can_add_item(status: SaleSessionStatus) -> bool:
    return status is SaleSessionStatus.OPEN


def can_commit(status: SaleSessionStatus | None) -> bool:
    return status is SaleSessionStatus.READY_TO_CHARGE


def classify_commit(
    active_status: SaleSessionStatus | None,
    *,
    confirmed_exists: bool,
) -> CommitKind:
    if active_status is SaleSessionStatus.READY_TO_CHARGE:
        return CommitKind.TRANSITION
    if active_status is SaleSessionStatus.OPEN:
        return CommitKind.NOT_READY
    if active_status is None and confirmed_exists:
        return CommitKind.READ_BACK
    return CommitKind.NOT_FOUND


def classify_totalize(status: SaleSessionStatus | None, item_count: int) -> TotalizeKind:
    if status is None or item_count < 1:
        return TotalizeKind.EMPTY
    if status is SaleSessionStatus.READY_TO_CHARGE:
        return TotalizeKind.READ_BACK
    if status is SaleSessionStatus.OPEN:
        return TotalizeKind.TRANSITION
    return TotalizeKind.EMPTY


def payment_amount_matches_total(amount: Money, items: list[SaleItem], *, currency: str = "MXN") -> bool:
    total = sum_session_total(items, currency=currency)
    return amount.amount == total.amount and amount.currency == total.currency


def sum_session_total(items: list[SaleItem], *, currency: str = "MXN") -> Money:
    if not items:
        return Money("0.00", currency)
    total = items[0].line_total.amount
    code = items[0].line_total.currency
    for item in items[1:]:
        total = total + item.line_total.amount
    return Money(total, code)
