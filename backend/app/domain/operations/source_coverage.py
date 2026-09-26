from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.domain.shared.errors import ValidationAppError

LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS = "only_lumo_registered_operations"
RECORDED_OPERATIONS_BASIS = "recorded_operations"


class CoverageDomain(StrEnum):
    SALES = "sales"
    CASH_COUNT = "cash_count"


class CoverageSourceType(StrEnum):
    MANUAL_CAPTURE = "manual_capture"


class CoverageStatus(StrEnum):
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class SourceCoverageRecord:
    """Lumo observed this domain from this source at least once for this day.

    The row is not completeness, freshness, health, or a percentage.
    """

    id: UUID
    business_id: UUID
    operational_day_id: UUID
    domain: CoverageDomain
    source_type: CoverageSourceType
    status: CoverageStatus
    limitation_code: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.domain, CoverageDomain):
            raise ValidationAppError("source coverage domain is not a Build A domain")
        if self.source_type is not CoverageSourceType.MANUAL_CAPTURE:
            raise ValidationAppError("source coverage source is manual_capture only")
        if self.status is not CoverageStatus.OBSERVED:
            raise ValidationAppError("source coverage status is observed only")
        if self.limitation_code != LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS:
            raise ValidationAppError("source coverage limitation is only_lumo_registered_operations")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValidationAppError("source coverage created_at must be timezone-aware")


def recorded_operations_declaration(records: list[SourceCoverageRecord] | tuple[SourceCoverageRecord, ...]) -> dict[str, Any]:
    """Pure projection. Empty coverage still returns the same limitation and a null declaration."""
    domains = sorted({record.domain.value for record in records})
    sources = sorted({record.source_type.value for record in records})
    return {
        "basis": RECORDED_OPERATIONS_BASIS,
        "domains": domains,
        "sources": sources,
        "limitation_code": LIMITATION_ONLY_LUMO_REGISTERED_OPERATIONS,
        "merchant_source_declaration": None,
    }
