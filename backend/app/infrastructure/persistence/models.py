from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class BusinessRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="es-MX")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    onboarding_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="completed", server_default=text("'completed'")
    )
    enabled_payment_methods: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)


class ActorBusinessLinkRow(Base):
    __tablename__ = "actor_business_links"
    __table_args__ = {"schema": "identity"}

    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class UserRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "identity"}

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class MembershipRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("business_id", "user_id", name="uq_memberships_business_user"),
        Index("ix_memberships_business_id", "business_id"),
        {"schema": "identity"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="owner")


class AuditEventRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_business_id", "business_id"),
        {"schema": "audit"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    route_or_tool: Mapped[str | None] = mapped_column(String(128), nullable=True)
    policy_decision: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    before_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class IdempotencyRecordRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "operation_type",
            "key",
            name="uq_idempotency_business_operation_key",
        ),
        CheckConstraint("status IN ('processing', 'completed', 'failed')", name="ck_idempotency_status"),
        {"schema": "platform"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="processing")
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class OutboxEventRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_events_business_id", "business_id"),
        {"schema": "platform"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class FoundationNoteRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "foundation_notes"
    __table_args__ = (
        Index("ix_foundation_notes_business_id", "business_id"),
        {"schema": "platform"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)


class ProductRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        Index("ix_products_business_id", "business_id"),
        CheckConstraint("sale_unit IN ('unit', 'package', 'kilogram')", name="ck_products_sale_unit"),
        CheckConstraint(
            "pricing_type IN ('per_unit', 'per_package', 'per_kilogram')",
            name="ck_products_pricing_type",
        ),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_products_status"),
        UniqueConstraint("id", "business_id", name="uq_products_id_business"),
        {"schema": "catalog"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    sale_unit: Mapped[str] = mapped_column(String(32), nullable=False)
    pricing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    current_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


class ProductAliasRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "product_aliases"
    __table_args__ = (
        Index("ix_product_aliases_business_id", "business_id"),
        {"schema": "catalog"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    product_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("catalog.products.id"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(200), nullable=False)


class OperationalDayRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "operational_days"
    __table_args__ = (
        UniqueConstraint("business_id", "business_date", name="uq_operational_days_business_date"),
        UniqueConstraint("id", "business_id", name="uq_operational_days_id_business"),
        Index("ix_operational_days_business_id", "business_id"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_operational_days_status"),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)


class CashCountRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cash_counts"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_cash_counts_id_business"),
        UniqueConstraint(
            "id",
            "business_id",
            "operational_day_id",
            name="uq_cash_counts_id_business_day",
        ),
        UniqueConstraint("supersedes_cash_count_id", name="uq_cash_counts_supersedes"),
        UniqueConstraint("superseded_by_id", name="uq_cash_counts_superseded_by"),
        Index("ix_cash_counts_business_id", "business_id"),
        Index("ix_cash_counts_operational_day_id", "operational_day_id"),
        Index(
            "uq_cash_counts_current",
            "operational_day_id",
            unique=True,
            postgresql_where=text("superseded_by_id IS NULL"),
        ),
        CheckConstraint("amount >= 0", name="ck_cash_counts_amount_non_negative"),
        CheckConstraint("source IN ('manual_capture')", name="ck_cash_counts_source"),
        CheckConstraint(
            "supersedes_cash_count_id IS DISTINCT FROM id",
            name="ck_cash_counts_supersedes_not_self",
        ),
        CheckConstraint(
            "superseded_by_id IS DISTINCT FROM id",
            name="ck_cash_counts_superseded_by_not_self",
        ),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_cash_counts_operational_day",
        ),
        ForeignKeyConstraint(
            ["supersedes_cash_count_id", "business_id"],
            ["operations.cash_counts.id", "operations.cash_counts.business_id"],
            name="fk_cash_counts_supersedes",
        ),
        ForeignKeyConstraint(
            ["superseded_by_id", "business_id"],
            ["operations.cash_counts.id", "operations.cash_counts.business_id"],
            name="fk_cash_counts_superseded_by",
            deferrable=True,
            initially="DEFERRED",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operational_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_capture")
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    supersedes_cash_count_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    superseded_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class ClosingSnapshotRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable close record. Application code inserts and reads; it never updates."""

    __tablename__ = "closing_snapshots"
    __table_args__ = (
        UniqueConstraint("operational_day_id", name="uq_closing_snapshots_operational_day"),
        UniqueConstraint("id", "business_id", name="uq_closing_snapshots_id_business"),
        UniqueConstraint(
            "id",
            "business_id",
            "operational_day_id",
            name="uq_closing_snapshots_id_business_day",
        ),
        UniqueConstraint("cash_count_id", name="uq_closing_snapshots_cash_count"),
        UniqueConstraint(
            "business_id",
            "transaction_sequence",
            name="uq_closing_snapshots_business_transaction_sequence",
        ),
        CheckConstraint("transaction_sequence >= 1", name="ck_closing_snapshots_transaction_sequence"),
        Index("ix_closing_snapshots_business_id", "business_id"),
        CheckConstraint("sale_count >= 0", name="ck_closing_snapshots_sale_count"),
        CheckConstraint(
            "gross_sales_total >= 0 AND cash_total >= 0 AND card_total >= 0 "
            "AND transfer_total >= 0 AND expected_cash >= 0 AND counted_cash >= 0",
            name="ck_closing_snapshots_money_non_negative",
        ),
        CheckConstraint("expected_cash = cash_total", name="ck_closing_snapshots_expected_is_cash"),
        CheckConstraint(
            "gross_sales_total = cash_total + card_total + transfer_total",
            name="ck_closing_snapshots_gross",
        ),
        CheckConstraint(
            "cash_difference = counted_cash - expected_cash",
            name="ck_closing_snapshots_difference",
        ),
        CheckConstraint(
            "(cash_difference > 0 AND cash_status = 'over') "
            "OR (cash_difference < 0 AND cash_status = 'short') "
            "OR (cash_difference = 0 AND cash_status = 'balanced')",
            name="ck_closing_snapshots_cash_status",
        ),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_closing_snapshots_operational_day",
        ),
        ForeignKeyConstraint(
            ["cash_count_id", "business_id", "operational_day_id"],
            ["operations.cash_counts.id", "operations.cash_counts.business_id", "operations.cash_counts.operational_day_id"],
            name="fk_closing_snapshots_cash_count",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operational_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    cash_count_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sale_count: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_sales_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    card_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transfer_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expected_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    counted_cash: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_difference: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cash_status: Mapped[str] = mapped_column(String(16), nullable=False)
    close_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transaction_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WorkItemRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_items"
    __table_args__ = (
        Index("ix_work_items_business_id", "business_id"),
        Index(
            "uq_work_items_one_open",
            "business_id",
            "operational_day_id",
            "type",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        CheckConstraint(
            "type IN ('cash_count_required', 'cash_difference_review', 'close_confirmation_required')",
            name="ck_work_items_type",
        ),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_work_items_status"),
        CheckConstraint("responsible_party = 'business'", name="ck_work_items_responsible_party"),
        CheckConstraint("source = 'daily_close_rule'", name="ck_work_items_source"),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="ck_work_items_evidence_object"),
        CheckConstraint(
            "("
            "type = 'cash_count_required' AND priority = 'critical' AND reason_code = 'cash_count_missing'"
            ") OR ("
            "type = 'cash_difference_review' AND priority = 'high' "
            "AND reason_code IN ('cash_short', 'cash_over')"
            ") OR ("
            "type = 'close_confirmation_required' AND priority = 'normal' "
            "AND reason_code = 'close_confirmation_required'"
            ")",
            name="ck_work_items_type_priority_reason",
        ),
        CheckConstraint(
            "resolution_actor_type IS NULL OR resolution_actor_type IN ('business', 'system')",
            name="ck_work_items_resolution_actor_type",
        ),
        CheckConstraint(
            "resolution_code IS NULL OR resolution_code IN ("
            "'cash_count_recorded', 'cash_balanced', 'day_closed', 'cash_unbalanced')",
            name="ck_work_items_resolution_code",
        ),
        CheckConstraint(
            "("
            "status = 'open' AND resolved_at IS NULL AND resolution_actor_type IS NULL "
            "AND resolved_by_actor_id IS NULL AND resolution_code IS NULL"
            ") OR ("
            "status = 'resolved' AND resolution_actor_type = 'business' AND resolved_at IS NOT NULL "
            "AND resolved_by_actor_id IS NOT NULL AND resolution_code IS NOT NULL"
            ") OR ("
            "status = 'resolved' AND resolution_actor_type = 'system' AND resolved_at IS NOT NULL "
            "AND resolved_by_actor_id IS NULL AND resolution_code IS NOT NULL"
            ")",
            name="ck_work_items_resolution",
        ),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_work_items_operational_day",
        ),
        ForeignKeyConstraint(
            ["outcome_run_id", "business_id", "operational_day_id"],
            [
                "operations.outcome_runs.id",
                "operations.outcome_runs.business_id",
                "operations.outcome_runs.operational_day_id",
            ],
            name="fk_work_items_outcome_run",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operational_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    responsible_party: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_actor_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolved_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolution_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome_run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class OutcomeRunRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outcome_runs"
    __table_args__ = (
        UniqueConstraint("id", "business_id", name="uq_outcome_runs_id_business"),
        UniqueConstraint(
            "id",
            "business_id",
            "operational_day_id",
            name="uq_outcome_runs_id_business_day",
        ),
        UniqueConstraint(
            "business_id",
            "operational_day_id",
            "outcome_type",
            "outcome_version",
            name="uq_outcome_runs_identity",
        ),
        Index("ix_outcome_runs_business_id", "business_id"),
        CheckConstraint("outcome_type = 'daily_close_ready'", name="ck_outcome_runs_type"),
        CheckConstraint("outcome_version = 1", name="ck_outcome_runs_version"),
        CheckConstraint("owner_type = 'business'", name="ck_outcome_runs_owner"),
        CheckConstraint(
            "status IN ('in_progress', 'ready', 'completed')",
            name="ck_outcome_runs_status",
        ),
        CheckConstraint(
            "reason_code IN ("
            "'awaiting_cash_count', 'ready_balanced', 'ready_cash_short', "
            "'ready_cash_over', 'closed_confirmed')",
            name="ck_outcome_runs_reason",
        ),
        CheckConstraint("jsonb_typeof(evidence) = 'object'", name="ck_outcome_runs_evidence_object"),
        CheckConstraint(
            "("
            "status = 'in_progress' AND reason_code = 'awaiting_cash_count' "
            "AND ready_at IS NULL AND completed_at IS NULL AND closing_snapshot_id IS NULL "
            "AND evidence->>'cash_status' = 'not_counted' "
            "AND NOT (evidence ? 'current_cash_count_id')"
            ") OR ("
            "status = 'ready' AND ready_at IS NOT NULL AND completed_at IS NULL "
            "AND closing_snapshot_id IS NULL AND ("
            "(reason_code = 'ready_balanced' AND evidence->>'cash_status' = 'balanced') "
            "OR (reason_code = 'ready_cash_short' AND evidence->>'cash_status' = 'short') "
            "OR (reason_code = 'ready_cash_over' AND evidence->>'cash_status' = 'over')"
            ") AND evidence ? 'current_cash_count_id'"
            ") OR ("
            "status = 'completed' AND reason_code = 'closed_confirmed' "
            "AND ready_at IS NOT NULL AND completed_at IS NOT NULL "
            "AND closing_snapshot_id IS NOT NULL "
            "AND evidence->>'cash_status' IN ('balanced', 'short', 'over') "
            "AND evidence ? 'current_cash_count_id'"
            ")",
            name="ck_outcome_runs_state",
        ),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_outcome_runs_operational_day",
        ),
        ForeignKeyConstraint(
            ["closing_snapshot_id", "business_id", "operational_day_id"],
            [
                "operations.closing_snapshots.id",
                "operations.closing_snapshots.business_id",
                "operations.closing_snapshots.operational_day_id",
            ],
            name="fk_outcome_runs_closing_snapshot",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operational_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closing_snapshot_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)


class WorkAbsorptionRecordRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "work_absorption_records"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "outcome_run_id",
            "task_type",
            name="uq_work_absorption_records_task",
        ),
        Index("ix_work_absorption_records_business_id", "business_id"),
        Index("ix_work_absorption_records_outcome_run_id", "outcome_run_id"),
        ForeignKeyConstraint(
            ["outcome_run_id", "business_id"],
            ["operations.outcome_runs.id", "operations.outcome_runs.business_id"],
            name="fk_work_absorption_outcome_run",
        ),
        ForeignKeyConstraint(
            ["work_item_id", "business_id"],
            ["operations.work_items.id", "operations.work_items.business_id"],
            name="fk_work_absorption_work_item",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    outcome_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    work_item_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    current_execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    human_steps_before: Mapped[int] = mapped_column(Integer, nullable=False)
    human_steps_after: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_minutes_saved: Mapped[int] = mapped_column(Integer, nullable=False)
    business_intervention_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_intervention_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    automation_level: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    baseline_version: Mapped[str] = mapped_column(String(128), nullable=False)


class OutcomeCostRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "outcome_costs"
    __table_args__ = (
        UniqueConstraint("business_id", "outcome_run_id", name="uq_outcome_costs_identity"),
        Index("ix_outcome_costs_business_id", "business_id"),
        Index("ix_outcome_costs_outcome_run_id", "outcome_run_id"),
        ForeignKeyConstraint(
            ["outcome_run_id", "business_id"],
            ["operations.outcome_runs.id", "operations.outcome_runs.business_id"],
            name="fk_outcome_costs_outcome_run",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    outcome_run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    model_call_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_call_count_status: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_token_status: Mapped[str] = mapped_column(String(16), nullable=False)
    model_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    model_cost_status: Mapped[str] = mapped_column(String(16), nullable=False)
    infrastructure_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    infrastructure_cost_status: Mapped[str] = mapped_column(String(16), nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count_status: Mapped[str] = mapped_column(String(16), nullable=False)
    business_intervention_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_intervention_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_total_cost_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_completeness: Mapped[str] = mapped_column(String(16), nullable=False)


class SourceCoverageRecordRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "source_coverage_records"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "operational_day_id",
            "domain",
            "source_type",
            name="uq_source_coverage_records_identity",
        ),
        Index("ix_source_coverage_records_business_id", "business_id"),
        CheckConstraint("domain IN ('sales', 'cash_count')", name="ck_source_coverage_records_domain"),
        CheckConstraint("source_type = 'manual_capture'", name="ck_source_coverage_records_source_type"),
        CheckConstraint("status = 'observed'", name="ck_source_coverage_records_status"),
        CheckConstraint(
            "limitation_code = 'only_lumo_registered_operations'",
            name="ck_source_coverage_records_limitation",
        ),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_source_coverage_records_operational_day",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operational_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    limitation_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BusinessEventRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "business_events"
    __table_args__ = (
        UniqueConstraint(
            "business_id",
            "event_type",
            "source_entity_type",
            "source_entity_id",
            name="uq_business_events_source",
        ),
        Index("ix_business_events_business_day", "business_id", "operational_day_id"),
        CheckConstraint("source_type = 'manual_capture'", name="ck_business_events_source_type"),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_business_events_operational_day",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    operational_day_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    facts: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PilotProgramEnrollmentRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pilot_program_enrollments"
    __table_args__ = (
        Index("ix_pilot_program_enrollments_business_id", "business_id"),
        CheckConstraint(
            "pilot_ended_on IS NULL OR pilot_ended_on >= pilot_started_on",
            name="ck_pilot_program_enrollments_dates",
        ),
        ForeignKeyConstraint(
            ["business_id"],
            ["identity.businesses.id"],
            name="fk_pilot_program_enrollments_business",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    cohort_code: Mapped[str] = mapped_column(String(64), nullable=False)
    pilot_started_on: Mapped[date] = mapped_column(Date, nullable=False)
    pilot_ended_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PilotPerceptionResponseRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "pilot_perception_responses"
    __table_args__ = (
        Index("ix_pilot_perception_responses_business_id", "business_id"),
        UniqueConstraint(
            "business_id",
            "capture_id",
            "question_code",
            name="uq_pilot_perception_responses_capture_question",
        ),
        CheckConstraint(
            "question_code IN ("
            "'close_organizer', 'information_delivery', 'product_category', 'workflow_ownership'"
            ")",
            name="ck_pilot_perception_question_code",
        ),
        CheckConstraint(
            "capture_source IN ('internal_interview', 'internal_import')",
            name="ck_pilot_perception_capture_source",
        ),
        CheckConstraint(
            "note IS NULL OR length(note) <= 500",
            name="ck_pilot_perception_note_length",
        ),
        ForeignKeyConstraint(
            ["business_id"],
            ["identity.businesses.id"],
            name="fk_pilot_perception_responses_business",
        ),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    capture_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    cohort_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_set_version: Mapped[str] = mapped_column(String(64), nullable=False)
    question_code: Mapped[str] = mapped_column(String(64), nullable=False)
    response_code: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capture_source: Mapped[str] = mapped_column(String(32), nullable=False)


class StageGateAssessmentRow(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "stage_gate_assessments"
    __table_args__ = (
        Index("ix_stage_gate_assessments_business_id", "business_id"),
        CheckConstraint("scope_type IN ('business', 'cohort')", name="ck_stage_gate_assessments_scope"),
        CheckConstraint("build_identifier = 'mvp_build_a'", name="ck_stage_gate_assessments_build"),
        CheckConstraint(
            "evidence_window_end >= evidence_window_start",
            name="ck_stage_gate_assessments_window",
        ),
        CheckConstraint(
            "(scope_type = 'business' AND business_id IS NOT NULL) OR "
            "(scope_type = 'cohort' AND business_id IS NULL)",
            name="ck_stage_gate_assessments_scope_business",
        ),
        CheckConstraint(
            "overall_status IN ('ready', 'not_ready', 'insufficient_evidence')",
            name="ck_stage_gate_assessments_overall",
        ),
        CheckConstraint("jsonb_typeof(criterion_results) = 'array'", name="ck_stage_gate_assessments_results"),
        CheckConstraint(
            "jsonb_typeof(included_outcome_run_refs) = 'array'",
            name="ck_stage_gate_assessments_refs",
        ),
        {"schema": "operations"},
    )

    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    business_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    cohort_code: Mapped[str] = mapped_column(String(64), nullable=False)
    build_identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    evidence_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    evidence_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    criterion_results: Mapped[list] = mapped_column(JSONB, nullable=False)
    included_outcome_run_refs: Mapped[list] = mapped_column(JSONB, nullable=False)
    included_business_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SaleSessionRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sale_sessions"
    __table_args__ = (
        Index("ix_sale_sessions_business_id", "business_id"),
        Index("ix_sale_sessions_operational_day_id", "operational_day_id"),
        CheckConstraint(
            "status IN ('open', 'ready_to_charge', 'confirmed', 'voided')",
            name="ck_sale_sessions_status",
        ),
        CheckConstraint(
            "(status IN ('confirmed', 'voided') AND operational_day_id IS NOT NULL AND confirmed_at IS NOT NULL) "
            "OR (status IN ('open', 'ready_to_charge') AND operational_day_id IS NULL AND confirmed_at IS NULL)",
            name="ck_sale_sessions_day_membership",
        ),
        CheckConstraint("sale_revision >= 1", name="ck_sale_sessions_sale_revision"),
        CheckConstraint(
            "(status = 'voided' AND voided_at IS NOT NULL AND voided_by_actor_id IS NOT NULL "
            "AND void_reason IS NOT NULL AND length(btrim(void_reason)) > 0 "
            "AND void_reason = btrim(void_reason)) "
            "OR (status <> 'voided' AND voided_at IS NULL AND voided_by_actor_id IS NULL AND void_reason IS NULL)",
            name="ck_sale_sessions_void_metadata",
        ),
        ForeignKeyConstraint(
            ["operational_day_id", "business_id"],
            ["operations.operational_days.id", "operations.operational_days.business_id"],
            name="fk_sale_sessions_operational_day",
        ),
        {"schema": "sales"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    sale_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    operational_day_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    transaction_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    void_transaction_sequence: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class BusinessTransactionCounterRow(Base):
    """Per-business monotonic counter shared by sale, void, and daily close (ADR-033)."""

    __tablename__ = "business_transaction_counters"
    __table_args__ = (
        CheckConstraint("last_value >= 0", name="ck_business_transaction_counters_last_value"),
        {"schema": "operations"},
    )

    business_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("identity.businesses.id"),
        primary_key=True,
    )
    last_value: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class SaleItemRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sale_items"
    __table_args__ = (
        Index("ix_sale_items_business_id", "business_id"),
        Index("ix_sale_items_session_id", "sale_session_id"),
        CheckConstraint(
            "(source_type = 'catalog' AND product_id IS NOT NULL) OR "
            "(source_type = 'free_concept' AND product_id IS NULL AND length(btrim(product_name_snapshot)) > 0)",
            name="ck_sale_items_source",
        ),
        CheckConstraint("unit_price > 0 AND line_total > 0", name="ck_sale_items_money_positive"),
        CheckConstraint(
            "(source_type = 'catalog' AND product_id IS NOT NULL AND catalog_unit_price_snapshot IS NOT NULL "
            "AND catalog_unit_price_snapshot > 0 AND unit_price = catalog_unit_price_snapshot "
            "AND price_override_reason IS NULL) OR "
            "(source_type = 'catalog' AND product_id IS NOT NULL AND catalog_unit_price_snapshot IS NOT NULL "
            "AND catalog_unit_price_snapshot > 0 AND unit_price <> catalog_unit_price_snapshot "
            "AND price_override_reason IS NOT NULL AND length(btrim(price_override_reason)) > 0 "
            "AND price_override_reason = btrim(price_override_reason)) OR "
            "(source_type = 'free_concept' AND product_id IS NULL AND catalog_unit_price_snapshot IS NULL "
            "AND price_override_reason IS NULL)",
            name="ck_sale_items_catalog_price",
        ),
        ForeignKeyConstraint(
            ["product_id", "business_id"],
            ["catalog.products.id", "catalog.products.business_id"],
            name="fk_sale_items_product_business",
        ),
        {"schema": "sales"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sale_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sales.sale_sessions.id"),
        nullable=False,
    )
    product_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("catalog.products.id"),
        nullable=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="catalog")
    product_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity_input: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    unit_input: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_normalized: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    unit_normalized: Mapped[str] = mapped_column(String(32), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    catalog_unit_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    price_override_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PaymentRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_business_id", "business_id"),
        UniqueConstraint("sale_session_id", name="uq_payments_sale_session_id"),
        CheckConstraint("method IN ('cash', 'card', 'transfer')", name="ck_payments_method"),
        CheckConstraint("status IN ('recorded')", name="ck_payments_status"),
        CheckConstraint("source IN ('manual_capture')", name="ck_payments_source"),
        {"schema": "sales"},
    )

    business_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sale_session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sales.sale_sessions.id"),
        nullable=False,
    )
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="recorded")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual_capture")
