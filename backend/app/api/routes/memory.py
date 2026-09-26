"""Read-only timeline of confirmed business events. No search parameters."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_tenant
from app.application.queries.get_factual_memory import FactualMemoryService
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository

router = APIRouter()

_ALLOWED_QUERY = frozenset({"limit", "before"})


@router.get("/api/v1/memory/events")
def list_memory_events(
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
    limit: int = 20,
    before: str | None = None,
) -> dict:
    unknown = set(request.query_params) - _ALLOWED_QUERY
    if unknown:
        raise ValidationAppError("unsupported memory query")
    return FactualMemoryService(
        identities=IdentityRepository(session),
        operations=OperationsRepository(session),
    ).list_timeline(tenant=tenant, limit=limit, before=before)
