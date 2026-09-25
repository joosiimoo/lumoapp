from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.application.ports import AuditService
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import AuditEventRow


class SqlAlchemyAuditService:
    def __init__(self, session: Session) -> None:
        self._session = session

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
        omit_actor: bool = False,
    ) -> None:
        self._session.add(
            AuditEventRow(
                business_id=tenant.business_id,
                actor_id=None if omit_actor else tenant.actor_id,
                action=action,
                route_or_tool=route_or_tool,
                policy_decision=policy_decision,
                before_payload=before_payload,
                after_payload=after_payload,
                result=result,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
            )
        )
