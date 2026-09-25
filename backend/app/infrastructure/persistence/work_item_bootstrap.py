from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.application.workflows.sync_daily_close_outcome import maintain_open_daily_close
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.audit import SqlAlchemyAuditService
from app.infrastructure.persistence.engine import create_session_factory
from app.infrastructure.persistence.operations import OperationsRepository
from app.infrastructure.persistence.repositories import IdentityRepository

_BOOTSTRAP_ACTOR = UUID(int=0)
_ROUTE = "work_item.bootstrap"
_OUTCOME_ROUTE = "outcome_run.bootstrap"
_ORIGIN = "rollout_bootstrap"


def bootstrap_open_today_work_items(*, admin_url: str, now: datetime | None = None) -> int:
    """Insert missing WorkItems for each business's open today. Idempotent."""
    engine = create_engine(_as_sqlalchemy_url(admin_url), pool_pre_ping=True, future=True)
    try:
        businesses = _list_businesses(engine)
        factory = create_session_factory(engine)
        inserted = 0
        for business_id, _timezone in businesses:
            session = factory()
            try:
                inserted += _initialize_one(session, business_id=business_id, now=now)
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        return inserted
    finally:
        engine.dispose()


def _initialize_one(session: Session, *, business_id: UUID, now: datetime | None) -> int:
    tenant = TenantContext(business_id=business_id, actor_id=_BOOTSTRAP_ACTOR)
    return maintain_open_daily_close(
        identities=IdentityRepository(session),
        operations=OperationsRepository(session),
        audit=SqlAlchemyAuditService(session),
        tenant=tenant,
        now=now,
        correlation_id=_ROUTE,
        idempotency_key=None,
        route_or_tool=_ROUTE,
        outcome_route_or_tool=_OUTCOME_ROUTE,
        origin=_ORIGIN,
        omit_actor=True,
    )


def _list_businesses(engine) -> list[tuple[UUID, str]]:
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        rows = connection.execute(text("SELECT id, timezone FROM identity.businesses")).all()
        connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))
    return [(row.id, row.timezone) for row in rows]


def _as_sqlalchemy_url(value: str) -> str:
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value
