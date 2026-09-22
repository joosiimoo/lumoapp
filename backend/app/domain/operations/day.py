from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class OperationalDayStatus(StrEnum):
    OPEN = "open"


@dataclass(frozen=True, slots=True)
class OperationalDay:
    id: UUID
    business_id: UUID
    business_date: date
    status: OperationalDayStatus
    timezone: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DaySummaryTotals:
    sale_count: int
    gross_sales_total: str
    cash_total: str
    card_total: str
    transfer_total: str
    currency: str
