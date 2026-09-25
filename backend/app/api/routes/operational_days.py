"""Authenticated download of one OperationalDay's confirmed sales."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_tenant
from app.application.queries.get_next_best_action import GetNextBestAction
from app.application.queries.export_daily_sales import ExportDailySales
from app.domain.shared.tenant import TenantContext
from app.infrastructure.export.daily_sales_csv import render_daily_sales_csv
from app.infrastructure.export.daily_sales_xlsx import render_daily_sales_xlsx
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository
from app.infrastructure.persistence.sales_export import SalesExportRepository

router = APIRouter()

_CSV_TYPE = "text/csv; charset=utf-8"
_XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/api/v1/operational-days/current/next-best-action")
def get_current_next_best_action(
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
) -> dict:
    identities = IdentityRepository(session)
    operations = OperationsRepository(session)
    return GetNextBestAction(identities=identities, operations=operations).execute(tenant=tenant)


@router.get("/api/v1/operational-days/{operational_day_ref}/sales-export")
def export_operational_day_sales(
    operational_day_ref: str,
    format: Literal["csv", "xlsx"],
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
) -> Response:
    export = ExportDailySales(
        identities=IdentityRepository(session),
        sales_export=SalesExportRepository(session),
    ).execute(tenant=tenant, operational_day_ref=operational_day_ref)
    if format == "csv":
        payload = render_daily_sales_csv(export)
        media_type = _CSV_TYPE
        filename = export.filename("csv")
    else:
        payload = render_daily_sales_xlsx(export)
        media_type = _XLSX_TYPE
        filename = export.filename("xlsx")
    return Response(
        content=payload,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
