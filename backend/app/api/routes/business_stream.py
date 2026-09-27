"""Read-only Business Stream for today. No writes and no model call."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_tenant
from app.application.queries.get_business_stream import GetBusinessStream
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository

router = APIRouter()


@router.get("/api/v1/business-stream/today")
def get_business_stream_today(
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
) -> dict:
    if request.query_params:
        raise ValidationAppError("This read does not accept query parameters")
    return GetBusinessStream(IdentityRepository(session), OperationsRepository(session)).execute(tenant=tenant)
