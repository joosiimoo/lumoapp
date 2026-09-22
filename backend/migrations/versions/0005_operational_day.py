"""Operational days and confirmed-sale membership.

Revision ID: 0005_operational_day
Revises: 0004_confirmed_payment
Create Date: 2026-09-21
"""

from __future__ import annotations

from datetime import UTC

from alembic import op
from sqlalchemy import text

from app.domain.operations import InvalidBusinessTimezone, business_date_for
from app.domain.shared.ids import new_uuid7

revision = "0005_operational_day"
down_revision = "0004_confirmed_payment"
branch_labels = None
depends_on = None

_RLS_TABLES = (
    "identity.businesses",
    "sales.sale_sessions",
    "operations.operational_days",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS operations")
    op.execute(
        """
        CREATE TABLE operations.operational_days (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            business_date DATE NOT NULL,
            status VARCHAR(32) NOT NULL,
            timezone VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_operational_days_status CHECK (status IN ('open')),
            CONSTRAINT uq_operational_days_business_date UNIQUE (business_id, business_date),
            CONSTRAINT uq_operational_days_id_business UNIQUE (id, business_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_operational_days_business_id ON operations.operational_days (business_id)")
    op.execute("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.operational_days
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute("GRANT USAGE ON SCHEMA operations TO lumo_app")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operations.operational_days TO lumo_app"
    )

    op.execute("ALTER TABLE sales.sale_sessions ADD COLUMN operational_day_id UUID NULL")
    op.execute("ALTER TABLE sales.sale_sessions ADD COLUMN confirmed_at TIMESTAMPTZ NULL")

    _backfill_legacy_confirmed_sales()

    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_day_membership
        CHECK (
            (status = 'confirmed' AND operational_day_id IS NOT NULL AND confirmed_at IS NOT NULL)
            OR (status IN ('open', 'ready_to_charge') AND operational_day_id IS NULL AND confirmed_at IS NULL)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT fk_sale_sessions_operational_day
        FOREIGN KEY (operational_day_id, business_id)
        REFERENCES operations.operational_days (id, business_id)
        """
    )
    op.execute(
        "CREATE INDEX ix_sale_sessions_operational_day_id ON sales.sale_sessions (operational_day_id)"
    )


def _disable_rls() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _restore_rls() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _backfill_legacy_confirmed_sales() -> None:
    bind = op.get_bind()
    _disable_rls()
    try:
        missing = bind.execute(
            text(
                """
                SELECT s.id
                FROM sales.sale_sessions s
                LEFT JOIN identity.businesses b ON b.id = s.business_id
                WHERE s.status = 'confirmed' AND (b.id IS NULL OR b.timezone IS NULL OR b.timezone = '')
                """
            )
        ).all()
        if missing:
            raise RuntimeError("confirmed sale is missing a business timezone")

        rows = bind.execute(
            text(
                """
                SELECT s.id AS session_id, s.business_id, s.updated_at, b.timezone
                FROM sales.sale_sessions s
                JOIN identity.businesses b ON b.id = s.business_id
                WHERE s.status = 'confirmed'
                """
            )
        ).mappings().all()

        grouped: dict[tuple, list] = {}
        for row in rows:
            legacy = row["updated_at"]
            if legacy is None or legacy.tzinfo is None or legacy.utcoffset() is None:
                raise RuntimeError("legacy confirmation timestamp must be timezone-aware")
            legacy_utc = legacy.astimezone(UTC)
            try:
                business_date = business_date_for(legacy_utc, row["timezone"])
            except (InvalidBusinessTimezone, ValueError) as exc:
                raise RuntimeError(f"invalid business timezone: {row['timezone']}") from exc
            grouped.setdefault((row["business_id"], business_date, row["timezone"]), []).append(
                {**row, "legacy_confirmed_at": legacy_utc}
            )

        for (business_id, business_date, timezone_name), sessions in grouped.items():
            legacy_opened_at = min(session["legacy_confirmed_at"] for session in sessions)
            day_id = new_uuid7()
            bind.execute(
                text(
                    """
                    INSERT INTO operations.operational_days (
                        id, business_id, business_date, status, timezone, created_at, updated_at
                    ) VALUES (
                        :id, :business_id, :business_date, 'open', :timezone, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": day_id,
                    "business_id": business_id,
                    "business_date": business_date,
                    "timezone": timezone_name,
                    "created_at": legacy_opened_at,
                    "updated_at": legacy_opened_at,
                },
            )
            for session in sessions:
                bind.execute(
                    text(
                        """
                        UPDATE sales.sale_sessions
                        SET confirmed_at = :confirmed_at,
                            operational_day_id = :operational_day_id
                        WHERE id = :session_id
                        """
                    ),
                    {
                        "confirmed_at": session["legacy_confirmed_at"],
                        "operational_day_id": day_id,
                        "session_id": session["session_id"],
                    },
                )

        leftover = bind.execute(
            text(
                """
                SELECT count(*)
                FROM sales.sale_sessions
                WHERE status = 'confirmed'
                  AND (operational_day_id IS NULL OR confirmed_at IS NULL)
                """
            )
        ).scalar_one()
        if leftover:
            raise RuntimeError("confirmed sessions remain without operational day membership")
    finally:
        _restore_rls()


def downgrade() -> None:
    op.execute(
        "ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS fk_sale_sessions_operational_day"
    )
    op.execute(
        "ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_day_membership"
    )
    op.execute("DROP INDEX IF EXISTS sales.ix_sale_sessions_operational_day_id")
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS operational_day_id")
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS confirmed_at")
    op.execute("DROP TABLE IF EXISTS operations.operational_days")
    op.execute("DROP SCHEMA IF EXISTS operations")
