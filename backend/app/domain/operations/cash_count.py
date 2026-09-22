from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from uuid import UUID

from app.domain.shared.errors import ValidationAppError

_TWO_PLACES = Decimal("0.01")
_AMOUNT = re.compile(r"^\$?(?P<digits>\d+)(?:\.(?P<fraction>\d{1,2}))?$")


class CashCountSource(StrEnum):
    MANUAL_CAPTURE = "manual_capture"


class CashStatus(StrEnum):
    NOT_COUNTED = "not_counted"
    BALANCED = "balanced"
    OVER = "over"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class CashCount:
    id: UUID
    business_id: UUID
    operational_day_id: UUID
    actor_id: UUID
    amount: Decimal
    currency: str
    source: CashCountSource
    counted_at: datetime
    supersedes_cash_count_id: UUID | None = None
    superseded_by_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def parse_counted_amount(raw: object) -> Decimal:
    """Parse a merchant-supplied cash amount. Deterministic, Decimal only."""
    if isinstance(raw, float):
        raise TypeError("counted amount must not use float")
    if isinstance(raw, Decimal):
        candidate = format(raw, "f")
    elif isinstance(raw, int) and not isinstance(raw, bool):
        candidate = str(raw)
    elif isinstance(raw, str):
        candidate = raw.strip().replace(",", ".")
    else:
        raise ValidationAppError("counted amount must be a decimal string")
    matched = _AMOUNT.match(candidate)
    if matched is None:
        raise ValidationAppError("counted amount must be a non-negative amount with at most two decimals")
    fraction = matched.group("fraction") or "00"
    try:
        value = Decimal(f"{matched.group('digits')}.{fraction}")
    except InvalidOperation as exc:  # pragma: no cover - regex already constrains the shape
        raise ValidationAppError("counted amount must be a decimal string") from exc
    return value.quantize(_TWO_PLACES)


def cash_difference(expected: Decimal | str, counted: Decimal | str | None) -> Decimal | None:
    """counted − expected, signed, two places. None when nothing was counted."""
    if counted is None:
        return None
    return (_decimal(counted) - _decimal(expected)).quantize(_TWO_PLACES)


def cash_status_for(difference: Decimal | None) -> CashStatus:
    if difference is None:
        return CashStatus.NOT_COUNTED
    if difference > 0:
        return CashStatus.OVER
    if difference < 0:
        return CashStatus.SHORT
    return CashStatus.BALANCED


def _decimal(value: Decimal | str) -> Decimal:
    if isinstance(value, float):
        raise TypeError("cash amounts must not use float")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation as exc:
            raise ValidationAppError("invalid decimal cash amount") from exc
    raise TypeError("cash amounts must be Decimal or decimal string")
