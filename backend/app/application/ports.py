from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from app.domain.shared.tenant import TenantContext


class AuditService(Protocol):
    def record(
        self,
        *,
        tenant: TenantContext,
        action: str,
        route_or_tool: str | None,
        result: str,
        correlation_id: str,
        idempotency_key: str | None = None,
        policy_decision: dict[str, Any] | None = None,
        before_payload: dict[str, Any] | None = None,
        after_payload: dict[str, Any] | None = None,
    ) -> None: ...


class IdempotencyService(Protocol):
    def begin(
        self,
        *,
        tenant: TenantContext,
        operation_type: str,
        key: str,
        request_hash: str,
    ) -> dict[str, Any] | None: ...

    def complete(
        self,
        *,
        tenant: TenantContext,
        operation_type: str,
        key: str,
        status_code: int,
        body: dict[str, Any],
    ) -> None: ...


class Outbox(Protocol):
    def enqueue(
        self,
        *,
        tenant: TenantContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> None: ...
