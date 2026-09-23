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

    def peek(
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


class CatalogPort(Protocol):
    def resolve(self, *, tenant: TenantContext, query: str) -> Any: ...

    def get(self, *, tenant: TenantContext, product_id: UUID) -> Any: ...


class SalesPort(Protocol):
    def get_open_session(self, *, tenant: TenantContext, conversation_id: str | None) -> Any: ...

    def get_active_session(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        for_update: bool = False,
    ) -> Any: ...

    def update_session_status(
        self,
        *,
        tenant: TenantContext,
        sale_session_id: UUID,
        status: Any,
    ) -> Any: ...

    def confirm_session(
        self,
        *,
        tenant: TenantContext,
        sale_session_id: UUID,
        operational_day_id: UUID,
        confirmed_at: Any,
    ) -> Any: ...

    def add_session(self, *, tenant: TenantContext, session: Any) -> Any: ...

    def add_item(self, *, tenant: TenantContext, item: Any) -> Any: ...

    def list_items(self, *, tenant: TenantContext, sale_session_id: UUID) -> list[Any]: ...

    def add_payment(self, *, tenant: TenantContext, payment: Any) -> Any: ...

    def get_payment_for_session(self, *, tenant: TenantContext, sale_session_id: UUID) -> Any: ...

    def get_latest_confirmed_session(self, *, tenant: TenantContext, conversation_id: str | None) -> Any: ...

    def get_session_by_id(
        self,
        *,
        tenant: TenantContext,
        sale_session_id: UUID,
        for_update: bool = False,
    ) -> Any: ...

    def has_newer_active_session(
        self,
        *,
        tenant: TenantContext,
        conversation_id: str | None,
        created_at: Any,
        session_id: UUID,
    ) -> bool: ...


class IdentityPort(Protocol):
    def get_business(self, tenant: TenantContext) -> Any: ...


class Outbox(Protocol):
    def enqueue(
        self,
        *,
        tenant: TenantContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> None: ...
