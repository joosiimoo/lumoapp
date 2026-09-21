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
