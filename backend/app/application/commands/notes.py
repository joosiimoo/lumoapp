from __future__ import annotations

from hashlib import sha256
from typing import Any
from uuid import UUID

from app.application.ports import AuditService, IdempotencyService, Outbox
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.repositories import FoundationNoteRepository, IdentityRepository


class SessionQuery:
    def __init__(self, identities: IdentityRepository) -> None:
        self._identities = identities

    def execute(self, tenant: TenantContext) -> dict[str, Any]:
        self._identities.require_membership(tenant)
        business = self._identities.get_business(tenant)
        actor = self._identities.get_actor(tenant)
        return {
            "actor": {"id": str(actor.id), "name": actor.name},
            "business": {
                "id": str(business.id),
                "name": business.name,
                "currency": business.currency,
                "timezone": business.timezone,
                "locale": business.locale,
            },
        }


class CreateFoundationNote:
    operation_type = "platform.note.create"

    def __init__(
        self,
        notes: FoundationNoteRepository,
        audit: AuditService,
        idempotency: IdempotencyService,
        outbox: Outbox,
    ) -> None:
        self._notes = notes
        self._audit = audit
        self._idempotency = idempotency
        self._outbox = outbox

    def execute(
        self,
        *,
        tenant: TenantContext,
        text: str,
        idempotency_key: str,
        correlation_id: str,
        fail_after_write: bool = False,
    ) -> dict[str, Any]:
        if not text.strip():
            raise ValidationAppError("text is required")
        request_hash = sha256(text.encode("utf-8")).hexdigest()
        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay["body"]
        note = self._notes.add(tenant=tenant, text=text)
        self._audit.record(
            tenant=tenant,
            action=self.operation_type,
            route_or_tool="POST /api/v1/platform/notes",
            result="committed",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            after_payload={"note_id": str(note.id)},
        )
        self._outbox.enqueue(
            tenant=tenant,
            event_type="platform.note.created",
            payload={"note_id": str(note.id), "business_id": str(tenant.business_id)},
        )
        if fail_after_write:
            raise RuntimeError("forced rollback")
        body = {"id": str(note.id), "text": note.text, "business_id": str(note.business_id)}
        self._idempotency.complete(
            tenant=tenant,
            operation_type=self.operation_type,
            key=idempotency_key,
            status_code=201,
            body=body,
        )
        return body


class GetFoundationNote:
    def __init__(self, notes: FoundationNoteRepository) -> None:
        self._notes = notes

    def execute(self, *, tenant: TenantContext, note_id: UUID) -> dict[str, Any]:
        note = self._notes.get(tenant=tenant, note_id=note_id)
        return {"id": str(note.id), "text": note.text, "business_id": str(note.business_id)}
