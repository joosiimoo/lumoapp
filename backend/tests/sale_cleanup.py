"""Consistent reset of committed conversational sale mutations.

Piecemeal DELETE of sales.sale_items / sales.sale_sessions (and later only
idempotency) left the live-clarify-2 audit + sale.item.added outbox rows
pointing at session/item ids that no longer exist. Reset MUST happen in one
transaction covering sales and related integrity rows, or use rollback.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import (
    AuditEventRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    SaleItemRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id

SALE_AUDIT_ACTIONS = ("sale.start@1", "sale.add_item@1")
SALE_OUTBOX_EVENT = "sale.item.added"
SALE_MESSAGE_OPERATION = "lumo.message.add_sale_item"


def clear_tenant_sale_mutations(session: Session, business_id) -> None:
    set_current_business_id(session, business_id)
    session.execute(SaleItemRow.__table__.delete().where(SaleItemRow.business_id == business_id))
    session.execute(SaleSessionRow.__table__.delete().where(SaleSessionRow.business_id == business_id))
    session.execute(
        OutboxEventRow.__table__.delete().where(
            OutboxEventRow.business_id == business_id,
            OutboxEventRow.event_type == SALE_OUTBOX_EVENT,
        )
    )
    session.execute(
        IdempotencyRecordRow.__table__.delete().where(
            IdempotencyRecordRow.business_id == business_id,
            IdempotencyRecordRow.operation_type == SALE_MESSAGE_OPERATION,
        )
    )
    session.execute(
        AuditEventRow.__table__.delete().where(
            AuditEventRow.business_id == business_id,
            AuditEventRow.action.in_(SALE_AUDIT_ACTIONS),
        )
    )
    session.commit()


def sale_integrity_orphans(session: Session, business_id) -> list[str]:
    set_current_business_id(session, business_id)
    session.expire_all()
    session_ids = {
        str(row.id)
        for row in session.scalars(select(SaleSessionRow).where(SaleSessionRow.business_id == business_id)).all()
    }
    item_ids = {
        str(row.id) for row in session.scalars(select(SaleItemRow).where(SaleItemRow.business_id == business_id)).all()
    }
    orphans: list[str] = []
    for event in session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == business_id,
            OutboxEventRow.event_type == SALE_OUTBOX_EVENT,
        )
    ).all():
        payload = event.payload or {}
        sid = payload.get("sale_session_id")
        iid = payload.get("sale_item_id")
        if sid not in session_ids or iid not in item_ids:
            orphans.append(f"outbox:{event.id}:session={sid}:item={iid}")
    for event in session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == business_id,
            AuditEventRow.action.in_(SALE_AUDIT_ACTIONS),
        )
    ).all():
        payload = event.after_payload or {}
        sid = payload.get("sale_session_id")
        iid = payload.get("sale_item_id")
        if sid and sid not in session_ids:
            orphans.append(f"audit:{event.id}:missing_session={sid}")
        if iid and iid not in item_ids:
            orphans.append(f"audit:{event.id}:missing_item={iid}")
    return orphans
