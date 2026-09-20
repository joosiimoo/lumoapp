from __future__ import annotations

from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.application.ports import IdempotencyService
from app.domain.shared.errors import IdempotencyConflictError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import IdempotencyRecordRow


class SqlAlchemyIdempotencyService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def begin(
        self,
        *,
        tenant: TenantContext,
        operation_type: str,
        key: str,
        request_hash: str,
    ) -> dict[str, Any] | None:
        lock_key = hash((str(tenant.business_id), operation_type, key)) & 0x7FFFFFFF
        self._session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": lock_key})
        existing = self._session.scalar(
            select(IdempotencyRecordRow).where(
                IdempotencyRecordRow.business_id == tenant.business_id,
                IdempotencyRecordRow.operation_type == operation_type,
                IdempotencyRecordRow.key == key,
            )
        )
        if existing is None:
            self._session.add(
                IdempotencyRecordRow(
                    business_id=tenant.business_id,
                    operation_type=operation_type,
                    key=key,
                    request_hash=request_hash,
                    status="processing",
                )
            )
            self._session.flush()
            return None
        if existing.request_hash != request_hash:
            raise IdempotencyConflictError("Idempotency key reused with a different payload")
        if existing.status == "completed" and existing.response_body is not None:
            return {
                "status_code": existing.response_status or 200,
                "body": existing.response_body,
            }
        if existing.status == "failed":
            existing.status = "processing"
            existing.request_hash = request_hash
            return None
        return None

    def complete(
        self,
        *,
        tenant: TenantContext,
        operation_type: str,
        key: str,
        status_code: int,
        body: dict[str, Any],
    ) -> None:
        record = self._session.scalar(
            select(IdempotencyRecordRow).where(
                IdempotencyRecordRow.business_id == tenant.business_id,
                IdempotencyRecordRow.operation_type == operation_type,
                IdempotencyRecordRow.key == key,
            )
        )
        if record is None:
            return
        record.status = "completed"
        record.response_status = status_code
        record.response_body = body
