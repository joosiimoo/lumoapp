"""Consistent reset of committed conversational sale mutations.

Piecemeal DELETE of sales.payments / sales.sale_items / sales.sale_sessions (and later only
idempotency) left audit + outbox rows pointing at session/item/payment ids that no longer
exist. Reset MUST happen in one transaction covering sales and related integrity rows, or
use rollback.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import (
    AuditEventRow,
    IdempotencyRecordRow,
    OutboxEventRow,
    PaymentRow,
    SaleItemRow,
    SaleSessionRow,
)
from app.infrastructure.persistence.rls import set_current_business_id

SALE_AUDIT_ACTIONS = ("sale.start@1", "sale.add_item@1", "sale.totalize@1", "sale.commit@1")
SALE_OUTBOX_EVENTS = (
    "sale.item.added",
    "sale.ready_to_charge",
    "sale.confirmed",
    "payment.recorded",
)
SALE_MESSAGE_OPERATIONS = (
    "lumo.message.add_sale_item",
    "lumo.message.totalize_sale",
    "lumo.message.commit_sale",
)
SALE_OUTBOX_EVENT = "sale.item.added"
SALE_MESSAGE_OPERATION = "lumo.message.add_sale_item"


def clear_tenant_sale_mutations(session: Session, business_id) -> None:
    set_current_business_id(session, business_id)
    session.execute(PaymentRow.__table__.delete().where(PaymentRow.business_id == business_id))
    session.execute(SaleItemRow.__table__.delete().where(SaleItemRow.business_id == business_id))
    session.execute(SaleSessionRow.__table__.delete().where(SaleSessionRow.business_id == business_id))
    session.execute(
        OutboxEventRow.__table__.delete().where(
            OutboxEventRow.business_id == business_id,
            OutboxEventRow.event_type.in_(SALE_OUTBOX_EVENTS),
        )
    )
    session.execute(
        IdempotencyRecordRow.__table__.delete().where(
            IdempotencyRecordRow.business_id == business_id,
            IdempotencyRecordRow.operation_type.in_(SALE_MESSAGE_OPERATIONS),
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
    payment_ids = {
        str(row.id) for row in session.scalars(select(PaymentRow).where(PaymentRow.business_id == business_id)).all()
    }
    orphans: list[str] = []
    for event in session.scalars(
        select(OutboxEventRow).where(
            OutboxEventRow.business_id == business_id,
            OutboxEventRow.event_type.in_(SALE_OUTBOX_EVENTS),
        )
    ).all():
        payload = event.payload or {}
        sid = payload.get("sale_session_id")
        iid = payload.get("sale_item_id")
        pid = payload.get("payment_id")
        if sid and sid not in session_ids:
            orphans.append(f"outbox:{event.id}:session={sid}:item={iid}:payment={pid}")
        if iid and iid not in item_ids:
            orphans.append(f"outbox:{event.id}:session={sid}:item={iid}:payment={pid}")
        if pid and pid not in payment_ids:
            orphans.append(f"outbox:{event.id}:missing_payment={pid}")
    for event in session.scalars(
        select(AuditEventRow).where(
            AuditEventRow.business_id == business_id,
            AuditEventRow.action.in_(SALE_AUDIT_ACTIONS),
        )
    ).all():
        payload = event.after_payload or {}
        sid = payload.get("sale_session_id")
        iid = payload.get("sale_item_id")
        pid = payload.get("payment_id")
        if sid and sid not in session_ids:
            orphans.append(f"audit:{event.id}:missing_session={sid}")
        if iid and iid not in item_ids:
            orphans.append(f"audit:{event.id}:missing_item={iid}")
        if pid and pid not in payment_ids:
            orphans.append(f"audit:{event.id}:missing_payment={pid}")
    return orphans
