from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.agent.orchestrator import FoundationOrchestrator
from app.api.dependencies import get_correlation_id, get_db, get_tenant
from app.application.workflows.add_catalog_sale_item import AddCatalogSaleItem
from app.domain.shared.errors import ForbiddenError, ValidationAppError
from app.domain.shared.ids import new_uuid7
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.audit import SqlAlchemyAuditService
from app.infrastructure.persistence.catalog_sales import CatalogRepository, SalesRepository
from app.infrastructure.persistence.idempotency import SqlAlchemyIdempotencyService
from app.infrastructure.persistence.outbox import SqlAlchemyOutbox
from app.infrastructure.persistence.repositories import IdentityRepository

router = APIRouter()


class LumoMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=128)
    client_context: dict | None = None


class LumoMessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: str
    status: str
    text: str
    ui: list[dict]
    correlation_id: str


@router.post("/api/v1/lumo/messages", response_model=LumoMessageResponse)
def post_lumo_message(
    payload: LumoMessageRequest,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str = Depends(get_correlation_id),
) -> dict:
    if not idempotency_key:
        raise ValidationAppError("Idempotency-Key is required")
    workflow = AddCatalogSaleItem(
        catalog=CatalogRepository(session),
        sales=SalesRepository(session),
        identities=IdentityRepository(session),
        audit=SqlAlchemyAuditService(session),
        idempotency=SqlAlchemyIdempotencyService(session),
        outbox=SqlAlchemyOutbox(session),
    )
    orchestrator = FoundationOrchestrator(
        provider=request.app.state.llm_provider,
        tools=request.app.state.tool_registry,
        policies=request.app.state.policies,
        workflow=workflow,
        ui_composer=request.app.state.generative_ui_composer,
        pending=getattr(request.app.state, "pending_clarifications", None),
    )
    settings = request.app.state.settings
    fail_after_write = (
        request.headers.get("x-debug-fail-after-write") == "1" and settings.allows_debug_fail_after_write
    )
    conversation_id = (payload.conversation_id or "").strip() or None
    response = orchestrator.handle(
        payload.message,
        {
            "tenant": tenant,
            "conversation_id": conversation_id,
            "idempotency_key": idempotency_key,
            "correlation_id": correlation_id,
            "fail_after_write": fail_after_write,
            "client_context": payload.client_context or {},
        },
    )
    return {
        "message_id": str(new_uuid7()),
        "status": "completed",
        "text": response.text,
        "ui": response.ui,
        "correlation_id": correlation_id,
    }


@router.get("/api/v1/dev/carrota-token")
def carrota_token(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    if not settings.allows_dev_tokens:
        raise ForbiddenError("dev tokens are not available")
    token = getattr(request.app.state, "carrota_token", None)
    if not token:
        raise ValidationAppError("Carrota seed is not available")
    return {"access_token": token, "token_type": "bearer"}
