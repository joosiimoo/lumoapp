from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.persistence.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utcnow


class BusinessRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = {"schema": "identity"}

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="es-MX")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")


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
        UniqueConstraint("cash_count_id", name="uq_closing_snapshots_cash_count"),
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
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SaleSessionRow(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sale_sessions"
    __table_args__ = (
        Index("ix_sale_sessions_business_id", "business_id"),
        Index("ix_sale_sessions_operational_day_id", "operational_day_id"),
        CheckConstraint("status IN ('open', 'ready_to_charge', 'confirmed')", name="ck_sale_sessions_status"),
        CheckConstraint(
            "(status = 'confirmed' AND operational_day_id IS NOT NULL AND confirmed_at IS NOT NULL) "
            "OR (status IN ('open', 'ready_to_charge') AND operational_day_id IS NULL AND confirmed_at IS NULL)",
            name="ck_sale_sessions_day_membership",
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
    operational_day_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


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
