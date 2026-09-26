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
    BusinessEventRow,
    CashCountRow,
    ClosingSnapshotRow,
    IdempotencyRecordRow,
    OperationalDayRow,
    OutcomeRunRow,
    OutboxEventRow,
    PaymentRow,
    SaleItemRow,
    SaleSessionRow,
    SourceCoverageRecordRow,
    WorkItemRow,
)
from app.infrastructure.persistence.rls import set_current_business_id

SALE_AUDIT_ACTIONS = (
    "sale.start@1",
    "sale.add_item@1",
    "sale.totalize@1",
    "sale.commit@1",
    "operational_day.opened",
    "closing.submit_cash_count@1",
    "closing.confirm@1",
    "work_item.created",
    "work_item.resolved",
    "outcome_run.created",
    "outcome_run.status_changed",
)
SALE_OUTBOX_EVENTS = (
    "sale.item.added",
    "sale.ready_to_charge",
    "sale.confirmed",
    "payment.recorded",
    "operational_day.opened",
    "cash_count.recorded",
    "closing.confirmed",
)
SALE_MESSAGE_OPERATIONS = (
    "lumo.message.add_sale_item",
    "lumo.message.totalize_sale",
    "lumo.message.commit_sale",
    "lumo.message.record_cash_count",
    "lumo.message.confirm_close",
)
SALE_OUTBOX_EVENT = "sale.item.added"
SALE_MESSAGE_OPERATION = "lumo.message.add_sale_item"


def _purge_rls_table(connection, table: str) -> None:
    from sqlalchemy import text

    if connection.execute(text("SELECT to_regclass(:name)"), {"name": table}).scalar() is None:
        return
    connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
    connection.execute(text(f"DELETE FROM {table}"))
    connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def discard_work_items(engine) -> None:
    """Test isolation. Product downgrade still aborts while any WorkItem exists."""
    from sqlalchemy import text

    with engine.begin() as connection:
        _purge_rls_table(connection, "operations.business_events")
        _purge_rls_table(connection, "operations.source_coverage_records")
        if connection.execute(text("SELECT to_regclass('operations.work_items')")).scalar() is not None:
            connection.execute(text("ALTER TABLE operations.work_items DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("DELETE FROM operations.work_items"))
            connection.execute(text("ALTER TABLE operations.work_items ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.work_items FORCE ROW LEVEL SECURITY"))
        if connection.execute(text("SELECT to_regclass('operations.outcome_runs')")).scalar() is None:
            return
        connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("DELETE FROM operations.outcome_runs"))
        connection.execute(text("ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY"))


def isolate_database_for_0007_downgrade(engine) -> None:
    """Test isolation only. Product downgrade must still refuse a real close.

    Deletes snapshots and reopens days so a later Alembic downgrade of this
    disposable database is not blocked by rows a previous test committed.
    """
    from sqlalchemy import text

    with engine.begin() as connection:
        _purge_rls_table(connection, "operations.business_events")
        _purge_rls_table(connection, "operations.source_coverage_records")
        has_sale_items = connection.execute(text("SELECT to_regclass('sales.sale_items')")).scalar()
        if has_sale_items is not None:
            has_reason = connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'sales' AND table_name = 'sale_items'
                          AND column_name = 'price_override_reason'
                    )
                    """
                )
            ).scalar_one()
            has_source = connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'sales' AND table_name = 'sale_items'
                          AND column_name = 'source_type'
                    )
                    """
                )
            ).scalar_one()
            if has_reason or has_source:
                connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
                if has_reason:
                    connection.execute(
                        text(
                            """
                            DELETE FROM sales.sale_items
                            WHERE source_type = 'catalog'
                              AND (
                                price_override_reason IS NOT NULL
                                OR catalog_unit_price_snapshot IS DISTINCT FROM unit_price
                              )
                            """
                        )
                    )
                if has_source:
                    connection.execute(
                        text("DELETE FROM sales.sale_items WHERE source_type = 'free_concept' OR product_id IS NULL")
                    )
                connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
                connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))
        if connection.execute(text("SELECT to_regclass('operations.work_items')")).scalar() is not None:
            connection.execute(text("ALTER TABLE operations.work_items DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("DELETE FROM operations.work_items"))
            connection.execute(text("ALTER TABLE operations.work_items ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.work_items FORCE ROW LEVEL SECURITY"))
        if connection.execute(text("SELECT to_regclass('operations.outcome_runs')")).scalar() is not None:
            connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("DELETE FROM operations.outcome_runs"))
            connection.execute(text("ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY"))
        if connection.execute(text("SELECT to_regclass('operations.closing_snapshots')")).scalar() is None:
            return
        connection.execute(text("ALTER TABLE operations.closing_snapshots DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("DELETE FROM operations.closing_snapshots"))
        connection.execute(text("UPDATE operations.operational_days SET status = 'open' WHERE status = 'closed'"))
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        connection.execute(text("ALTER TABLE operations.closing_snapshots ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.closing_snapshots FORCE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY"))


def clear_tenant_sale_mutations(session: Session, business_id) -> None:
    set_current_business_id(session, business_id)
    session.execute(PaymentRow.__table__.delete().where(PaymentRow.business_id == business_id))
    session.execute(SaleItemRow.__table__.delete().where(SaleItemRow.business_id == business_id))
    session.execute(SaleSessionRow.__table__.delete().where(SaleSessionRow.business_id == business_id))
    session.execute(WorkItemRow.__table__.delete().where(WorkItemRow.business_id == business_id))
    session.execute(OutcomeRunRow.__table__.delete().where(OutcomeRunRow.business_id == business_id))
    session.execute(ClosingSnapshotRow.__table__.delete().where(ClosingSnapshotRow.business_id == business_id))
    session.execute(CashCountRow.__table__.delete().where(CashCountRow.business_id == business_id))
    session.execute(BusinessEventRow.__table__.delete().where(BusinessEventRow.business_id == business_id))
    session.execute(
        SourceCoverageRecordRow.__table__.delete().where(SourceCoverageRecordRow.business_id == business_id)
    )
    session.execute(OperationalDayRow.__table__.delete().where(OperationalDayRow.business_id == business_id))
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
    day_ids = {
        str(row.id)
        for row in session.scalars(select(OperationalDayRow).where(OperationalDayRow.business_id == business_id)).all()
    }
    cash_counts = session.scalars(
        select(CashCountRow).where(CashCountRow.business_id == business_id)
    ).all()
    cash_count_ids = {str(row.id) for row in cash_counts}
    orphans: list[str] = []
    current_per_day: dict[str, int] = {}
    for count in cash_counts:
        if str(count.operational_day_id) not in day_ids:
            orphans.append(f"cash_count:{count.id}:missing_day={count.operational_day_id}")
        # Under this tenant's RLS a link into another business is indistinguishable from a link
        # into nothing: either way the (id, business_id) pair is invisible here, and both are wrong.
        for column, value in (
            ("supersedes", count.supersedes_cash_count_id),
            ("superseded_by", count.superseded_by_id),
        ):
            if value is not None and str(value) not in cash_count_ids:
                orphans.append(f"cash_count:{count.id}:{column}_broken_or_cross_tenant={value}")
        if count.superseded_by_id is None:
            key = str(count.operational_day_id)
            current_per_day[key] = current_per_day.get(key, 0) + 1
    for day_id, current in current_per_day.items():
        if current > 1:
            orphans.append(f"cash_count:day={day_id}:current_rows={current}")
    snapshots = session.scalars(
        select(ClosingSnapshotRow).where(ClosingSnapshotRow.business_id == business_id)
    ).all()
    snapshots_per_day: dict[str, int] = {}
    current_count_ids = {str(count.id) for count in cash_counts if count.superseded_by_id is None}
    days_by_id = {
        str(row.id): row
        for row in session.scalars(select(OperationalDayRow).where(OperationalDayRow.business_id == business_id)).all()
    }
    for snapshot in snapshots:
        day_key = str(snapshot.operational_day_id)
        snapshots_per_day[day_key] = snapshots_per_day.get(day_key, 0) + 1
        day = days_by_id.get(day_key)
        if day is None or day.business_id != snapshot.business_id:
            orphans.append(f"snapshot:{snapshot.id}:missing_or_cross_tenant_day={snapshot.operational_day_id}")
        if str(snapshot.cash_count_id) not in cash_count_ids:
            orphans.append(f"snapshot:{snapshot.id}:missing_or_cross_tenant_count={snapshot.cash_count_id}")
        elif str(snapshot.cash_count_id) not in current_count_ids:
            orphans.append(f"snapshot:{snapshot.id}:count_not_current={snapshot.cash_count_id}")
        matching = next((count for count in cash_counts if str(count.id) == str(snapshot.cash_count_id)), None)
        if matching is not None and matching.operational_day_id != snapshot.operational_day_id:
            orphans.append(f"snapshot:{snapshot.id}:count_day_mismatch")
        if snapshot.expected_cash != snapshot.cash_total:
            orphans.append(f"snapshot:{snapshot.id}:expected_cash")
        if snapshot.gross_sales_total != snapshot.cash_total + snapshot.card_total + snapshot.transfer_total:
            orphans.append(f"snapshot:{snapshot.id}:gross")
        if snapshot.cash_difference != snapshot.counted_cash - snapshot.expected_cash:
            orphans.append(f"snapshot:{snapshot.id}:difference")
        sign = (
            "over"
            if snapshot.cash_difference > 0
            else "short"
            if snapshot.cash_difference < 0
            else "balanced"
        )
        if snapshot.cash_status != sign or snapshot.sale_count < 0:
            orphans.append(f"snapshot:{snapshot.id}:inconsistent")
    for day_id, count in snapshots_per_day.items():
        if count != 1:
            orphans.append(f"snapshot:day={day_id}:rows={count}")
    for day in days_by_id.values():
        present = snapshots_per_day.get(str(day.id), 0)
        if day.status == "closed" and present != 1:
            orphans.append(f"day:{day.id}:closed_snapshots={present}")
        if day.status == "open" and present != 0:
            orphans.append(f"day:{day.id}:open_snapshots={present}")
    for sale in session.scalars(select(SaleSessionRow).where(SaleSessionRow.business_id == business_id)).all():
        if sale.operational_day_id is not None and str(sale.operational_day_id) not in day_ids:
            orphans.append(f"session:{sale.id}:missing_day={sale.operational_day_id}")
        if sale.status == "confirmed" and (sale.operational_day_id is None or sale.confirmed_at is None):
            orphans.append(f"session:{sale.id}:confirmed_without_membership")
        if sale.status in {"open", "ready_to_charge"} and (
            sale.operational_day_id is not None or sale.confirmed_at is not None
        ):
            orphans.append(f"session:{sale.id}:active_with_membership")
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
        did = payload.get("operational_day_id")
        if sid and sid not in session_ids:
            orphans.append(f"outbox:{event.id}:session={sid}:item={iid}:payment={pid}")
        if iid and iid not in item_ids:
            orphans.append(f"outbox:{event.id}:session={sid}:item={iid}:payment={pid}")
        if pid and pid not in payment_ids:
            orphans.append(f"outbox:{event.id}:missing_payment={pid}")
        if did and did not in day_ids:
            orphans.append(f"outbox:{event.id}:missing_day={did}")
        ccid = payload.get("cash_count_id")
        if ccid and ccid not in cash_count_ids:
            orphans.append(f"outbox:{event.id}:missing_cash_count={ccid}")
        snap = payload.get("closing_snapshot_id")
        snapshot_ids = {str(row.id) for row in snapshots}
        if snap and snap not in snapshot_ids:
            orphans.append(f"outbox:{event.id}:missing_snapshot={snap}")
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
        did = payload.get("operational_day_id")
        if sid and sid not in session_ids:
            orphans.append(f"audit:{event.id}:missing_session={sid}")
        if iid and iid not in item_ids:
            orphans.append(f"audit:{event.id}:missing_item={iid}")
        if pid and pid not in payment_ids:
            orphans.append(f"audit:{event.id}:missing_payment={pid}")
        if did and did not in day_ids:
            orphans.append(f"audit:{event.id}:missing_day={did}")
        ccid = payload.get("cash_count_id")
        if ccid and ccid not in cash_count_ids:
            orphans.append(f"audit:{event.id}:missing_cash_count={ccid}")
        snap = payload.get("closing_snapshot_id")
        if snap and snap not in {str(row.id) for row in snapshots}:
            orphans.append(f"audit:{event.id}:missing_snapshot={snap}")
    outcomes = session.scalars(select(OutcomeRunRow).where(OutcomeRunRow.business_id == business_id)).all()
    work_items = session.scalars(select(WorkItemRow).where(WorkItemRow.business_id == business_id)).all()
    snapshot_ids = {str(row.id) for row in snapshots}
    snapshots_by_day = {str(row.operational_day_id): str(row.id) for row in snapshots}
    identity_counts: dict[tuple[str, str, int], int] = {}
    for run in outcomes:
        day_key = str(run.operational_day_id)
        identity = (day_key, run.outcome_type, run.outcome_version)
        identity_counts[identity] = identity_counts.get(identity, 0) + 1
        day = days_by_id.get(day_key)
        if day is None or day.business_id != run.business_id:
            orphans.append(f"outcome:{run.id}:missing_or_cross_tenant_day={run.operational_day_id}")
            continue
        if run.status == "completed":
            if day.status != "closed":
                orphans.append(f"outcome:{run.id}:completed_on_open_day")
            if run.completed_at is None or run.ready_at is None:
                orphans.append(f"outcome:{run.id}:completed_timestamps")
            if run.reason_code != "closed_confirmed":
                orphans.append(f"outcome:{run.id}:completed_reason")
            expected_snapshot = snapshots_by_day.get(day_key)
            if run.closing_snapshot_id is None or str(run.closing_snapshot_id) != expected_snapshot:
                orphans.append(f"outcome:{run.id}:snapshot_mismatch")
            elif str(run.closing_snapshot_id) not in snapshot_ids:
                orphans.append(f"outcome:{run.id}:missing_snapshot")
            if any(
                item.operational_day_id == run.operational_day_id and item.status == "open"
                for item in work_items
            ):
                orphans.append(f"outcome:{run.id}:open_work_item")
        if day.status == "open" and run.status == "completed":
            orphans.append(f"outcome:{run.id}:open_day_completed")
    for identity, count in identity_counts.items():
        if count > 1:
            orphans.append(f"outcome:day={identity[0]}:rows={count}")
    return orphans
