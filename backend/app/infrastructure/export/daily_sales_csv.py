"""RFC 4180 CSV adapter for one OperationalDay sales export."""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.application.queries.export_daily_sales import SalesExport, SalesExportLine
from app.infrastructure.export.columns import EXPORT_COLUMNS


def render_daily_sales_csv(export: SalesExport) -> bytes:
    zone = ZoneInfo(export.timezone_name)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, dialect="excel", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(EXPORT_COLUMNS)
    for line in export.lines:
        writer.writerow(_row(line, zone))
    return buffer.getvalue().encode("utf-8-sig")


def _row(line: SalesExportLine, zone: ZoneInfo) -> list[str]:
    local = line.sale_confirmed_at.astimezone(zone)
    return [
        line.business_date.isoformat(),
        str(line.sale_session_id),
        local.isoformat(timespec="seconds"),
        str(line.sale_item_id),
        line.product_name,
        line.source_type,
        "" if line.product_id is None else str(line.product_id),
        _quantity(line.quantity),
        line.unit,
        "" if line.catalog_unit_price is None else _money(line.catalog_unit_price),
        _money(line.unit_price),
        line.price_override_reason or "",
        _money(line.line_total),
        line.currency,
        str(line.payment_id),
        line.payment_method,
        _money(line.payment_amount),
    ]


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _quantity(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
