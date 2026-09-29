from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def set_current_actor_id(session: Session, actor_id: UUID) -> None:
    if not session.in_transaction():
        session.begin()
    session.execute(
        text("SELECT set_config('app.current_actor_id', :actor_id, true)"),
        {"actor_id": str(actor_id)},
    )


def set_current_business_id(session: Session, business_id: UUID) -> None:
    if not session.in_transaction():
        session.begin()
    session.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )
