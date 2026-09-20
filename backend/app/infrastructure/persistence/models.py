from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
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
