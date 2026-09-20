from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db, get_tenant
from app.api.schemas.platform import CreateNoteRequest, NoteResponse, SessionResponse
from app.application.commands.notes import CreateFoundationNote, GetFoundationNote, SessionQuery
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.audit import SqlAlchemyAuditService
from app.infrastructure.persistence.idempotency import SqlAlchemyIdempotencyService
from app.infrastructure.persistence.outbox import SqlAlchemyOutbox
from app.infrastructure.persistence.repositories import FoundationNoteRepository, IdentityRepository

router = APIRouter()


@router.api_route("/api/v1/audit/events/{event_id}", methods=["DELETE", "PATCH", "PUT"])
def mutate_audit(event_id: UUID) -> None:
    _ = event_id
    raise ValidationAppError("audit events are append-only")


@router.get("/api/v1/session", response_model=SessionResponse)
def get_session(
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
) -> dict:
    identities = IdentityRepository(session)
    return SessionQuery(identities).execute(tenant)


@router.post("/api/v1/platform/notes", status_code=201, response_model=NoteResponse)
def create_note(
    payload: CreateNoteRequest,
    request: Request,
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str = Depends(get_correlation_id),
) -> dict:
    if not idempotency_key:
        raise ValidationAppError("Idempotency-Key is required")
    _ = payload.business_id
    _ = request
    notes = FoundationNoteRepository(session)
    command = CreateFoundationNote(
        notes=notes,
        audit=SqlAlchemyAuditService(session),
        idempotency=SqlAlchemyIdempotencyService(session),
        outbox=SqlAlchemyOutbox(session),
    )
    fail_after_write = request.headers.get("x-debug-fail-after-write") == "1"
    return command.execute(
        tenant=tenant,
        text=payload.text,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
        fail_after_write=fail_after_write,
    )


@router.get("/api/v1/platform/notes/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: UUID,
    tenant: TenantContext = Depends(get_tenant),
    session: Session = Depends(get_db),
) -> dict:
    return GetFoundationNote(FoundationNoteRepository(session)).execute(tenant=tenant, note_id=note_id)
