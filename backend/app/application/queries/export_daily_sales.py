"""Resolve one OperationalDay and return its confirmed sale lines."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.application.ports import IdentityPort
from app.domain.operations import InvalidBusinessTimezone, business_date_for
from app.domain.shared.errors import InternalError, TenantScopeViolationError, ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.base import utcnow
from app.infrastructure.persistence.sales_export import ExportDayRead, ExportLineRead, SalesExportRepository


@dataclass(frozen=True, slots=True)
class SalesExportLine:
    business_date: date
    sale_session_id: UUID
    sale_confirmed_at: datetime
    sale_item_id: UUID
    product_name: str
    source_type: str
    product_id: UUID | None
    quantity: Decimal
    unit: str
    catalog_unit_price: Decimal | None
    unit_price: Decimal
    price_override_reason: str | None
    line_total: Decimal
    currency: str
    payment_id: UUID
    payment_method: str
    payment_amount: Decimal


@dataclass(frozen=True, slots=True)
class SalesExport:
    business_name: str
    business_date: date
    timezone_name: str
    currency: str
    status: str
    lines: tuple[SalesExportLine, ...]

    def filename(self, extension: str) -> str:
        return f"lumo-{business_slug(self.business_name)}-ventas-{self.business_date.isoformat()}.{extension}"


class ExportDailySales:
    def __init__(self, *, identities: IdentityPort, sales_export: SalesExportRepository) -> None:
        self._identities = identities
        self._sales_export = sales_export

    def execute(
        self,
        *,
        tenant: TenantContext,
        operational_day_ref: str,
        now: datetime | None = None,
    ) -> SalesExport:
        if operational_day_ref == "current":
            loaded = self._load_current(tenant, now)
        else:
            try:
                day_id = UUID(operational_day_ref)
            except ValueError as exc:
                raise ValidationAppError("operational day ref is invalid") from exc
            loaded = self._sales_export.load(tenant=tenant, day_id=day_id)
        if loaded is None:
            raise TenantScopeViolationError("operational day not found")
        self._require_consistent(loaded)
        try:
            ZoneInfo(loaded.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise InternalError("operational day timezone is invalid") from exc
        return SalesExport(
            business_name=loaded.business_name,
            business_date=loaded.business_date,
            timezone_name=loaded.timezone_name,
            currency=loaded.business_currency,
            status=loaded.status,
            lines=tuple(_to_line(loaded, line) for line in loaded.lines),
        )

    def _load_current(self, tenant: TenantContext, now: datetime | None) -> ExportDayRead | None:
        business = self._identities.get_business(tenant)
        instant = now if now is not None else utcnow()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValidationAppError("clock must be timezone-aware UTC")
        instant = instant.astimezone(UTC)
        try:
            business_date = business_date_for(instant, business.timezone)
        except InvalidBusinessTimezone as exc:
            raise ValidationAppError("invalid business timezone") from exc
        return self._sales_export.load(tenant=tenant, business_date=business_date)

    def _require_consistent(self, loaded: ExportDayRead) -> None:
        if loaded.broken_sale_count or any(line.payment_id is None for line in loaded.lines):
            raise InternalError("confirmed sales export is inconsistent")
        for line in loaded.lines:
            if line.currency != loaded.business_currency or line.payment_currency != loaded.business_currency:
                raise ValidationAppError("payment currency does not match the business")


def business_slug(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(character for character in folded if not unicodedata.combining(character))
    folded = folded.lower()
    folded = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    folded = folded[:40].strip("-")
    return folded or "negocio"


def _to_line(loaded: ExportDayRead, line: ExportLineRead) -> SalesExportLine:
    if line.payment_id is None or line.payment_method is None or line.payment_amount is None:
        raise InternalError("confirmed sales export is inconsistent")
    return SalesExportLine(
        business_date=loaded.business_date,
        sale_session_id=line.sale_session_id,
        sale_confirmed_at=line.sale_confirmed_at,
        sale_item_id=line.sale_item_id,
        product_name=line.product_name,
        source_type=line.source_type,
        product_id=line.product_id,
        quantity=line.quantity,
        unit=line.unit,
        catalog_unit_price=line.catalog_unit_price,
        unit_price=line.unit_price,
        price_override_reason=line.price_override_reason,
        line_total=line.line_total,
        currency=line.currency,
        payment_id=line.payment_id,
        payment_method=line.payment_method,
        payment_amount=line.payment_amount,
    )
