from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
from uuid import UUID

from app.domain.operations.cash_count import CashStatus
from app.domain.shared.errors import ValidationAppError

_TWO_PLACES = Decimal("0.01")
_SNAPSHOT_STATUSES = frozenset({CashStatus.BALANCED, CashStatus.OVER, CashStatus.SHORT})


@dataclass(frozen=True, slots=True)
class ClosingSnapshot:
    id: UUID
    business_id: UUID
    operational_day_id: UUID
    cash_count_id: UUID
    actor_id: UUID
    business_date: date
    currency: str
    sale_count: int
    gross_sales_total: Decimal
    cash_total: Decimal
    card_total: Decimal
    transfer_total: Decimal
    expected_cash: Decimal
    counted_cash: Decimal
    cash_difference: Decimal
    cash_status: CashStatus
    closed_at: datetime
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if self.cash_status not in _SNAPSHOT_STATUSES:
            raise ValidationAppError("a closing snapshot cannot be not_counted")
        if self.sale_count < 0:
            raise ValidationAppError("sale_count must be non-negative")
        expected = _money(self.expected_cash)
        cash = _money(self.cash_total)
        card = _money(self.card_total)
        transfer = _money(self.transfer_total)
        gross = _money(self.gross_sales_total)
        counted = _money(self.counted_cash)
        difference = _money(self.cash_difference)
        if any(amount < 0 for amount in (expected, cash, card, transfer, gross, counted)):
            raise ValidationAppError("snapshot money amounts except the difference must be non-negative")
        if expected != cash:
            raise ValidationAppError("expected_cash must equal cash_total")
        if gross != (cash + card + transfer).quantize(_TWO_PLACES):
            raise ValidationAppError("gross_sales_total must equal cash, card, and transfer")
        if difference != (counted - expected).quantize(_TWO_PLACES):
            raise ValidationAppError("cash_difference must equal counted_cash - expected_cash")
        if self.cash_status is not status_for_difference(difference):
            raise ValidationAppError("cash_status must match the sign of cash_difference")
        if self.created_at != self.closed_at or self.updated_at != self.closed_at:
            raise ValidationAppError("created_at and updated_at must equal closed_at")
        object.__setattr__(self, "gross_sales_total", gross)
        object.__setattr__(self, "cash_total", cash)
        object.__setattr__(self, "card_total", card)
        object.__setattr__(self, "transfer_total", transfer)
        object.__setattr__(self, "expected_cash", expected)
        object.__setattr__(self, "counted_cash", counted)
        object.__setattr__(self, "cash_difference", difference)


def status_for_difference(difference: Decimal) -> CashStatus:
    quantized = _money(difference)
    if quantized > 0:
        return CashStatus.OVER
    if quantized < 0:
        return CashStatus.SHORT
    return CashStatus.BALANCED


def preparation_fingerprint(
    *,
    business_id: UUID,
    operational_day_id: UUID,
    cash_count_id: UUID,
    business_date: date,
    currency: str,
    sale_count: int,
    gross_sales_total: Decimal | str,
    cash_total: Decimal | str,
    card_total: Decimal | str,
    transfer_total: Decimal | str,
    expected_cash: Decimal | str,
    counted_cash: Decimal | str,
    cash_difference: Decimal | str,
    cash_status: str,
) -> str:
    """SHA-256 hex of the approved v1 canonical string. No JWT and no binary float."""
    canonical = "|".join(
        [
            "v1",
            str(business_id),
            str(operational_day_id),
            str(cash_count_id),
            business_date.isoformat(),
            currency,
            str(sale_count),
            _money_text(gross_sales_total),
            _money_text(cash_total),
            _money_text(card_total),
            _money_text(transfer_total),
            _money_text(expected_cash),
            _money_text(counted_cash),
            _money_text(cash_difference),
            cash_status,
        ]
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _money(value: Decimal | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("snapshot amounts must not use float")
    if isinstance(value, Decimal):
        amount = value
    elif isinstance(value, str):
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValidationAppError("invalid decimal snapshot amount") from exc
    else:
        raise TypeError("snapshot amounts must be Decimal or decimal string")
    return amount.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _money_text(value: Decimal | str) -> str:
    return f"{_money(value):.2f}"
