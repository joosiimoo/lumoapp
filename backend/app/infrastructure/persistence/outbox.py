from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.application.ports import Outbox
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.models import OutboxEventRow


class SqlAlchemyOutbox:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        *,
        tenant: TenantContext,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        self._session.add(
            OutboxEventRow(
                business_id=tenant.business_id,
                event_type=event_type,
                payload=payload,
            )
        )
