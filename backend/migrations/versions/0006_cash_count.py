"""Cash counts for daily close preparation.

Revision ID: 0006_cash_count
Revises: 0005_operational_day
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision = "0006_cash_count"
down_revision = "0005_operational_day"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE operations.cash_counts (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operational_day_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            source VARCHAR(32) NOT NULL,
            counted_at TIMESTAMPTZ NOT NULL,
            supersedes_cash_count_id UUID NULL,
            superseded_by_id UUID NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_cash_counts_amount_non_negative CHECK (amount >= 0),
            CONSTRAINT ck_cash_counts_source CHECK (source IN ('manual_capture')),
            CONSTRAINT ck_cash_counts_supersedes_not_self CHECK (supersedes_cash_count_id IS DISTINCT FROM id),
            CONSTRAINT ck_cash_counts_superseded_by_not_self CHECK (superseded_by_id IS DISTINCT FROM id),
            CONSTRAINT uq_cash_counts_id_business UNIQUE (id, business_id),
            CONSTRAINT uq_cash_counts_supersedes UNIQUE (supersedes_cash_count_id),
            CONSTRAINT uq_cash_counts_superseded_by UNIQUE (superseded_by_id),
            CONSTRAINT fk_cash_counts_operational_day
                FOREIGN KEY (operational_day_id, business_id)
                REFERENCES operations.operational_days (id, business_id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_cash_counts_current
        ON operations.cash_counts (operational_day_id)
        WHERE superseded_by_id IS NULL
        """
    )
    op.execute("CREATE INDEX ix_cash_counts_business_id ON operations.cash_counts (business_id)")
    op.execute(
        "CREATE INDEX ix_cash_counts_operational_day_id ON operations.cash_counts (operational_day_id)"
    )

    # Tenant-safe self references. uq_cash_counts_id_business above is their target, so a supersede
    # link can never resolve to another business's row. superseded_by is deferred because a recount
    # retires the previous row before the replacement row exists.
    op.execute(
        """
        ALTER TABLE operations.cash_counts
        ADD CONSTRAINT fk_cash_counts_supersedes
        FOREIGN KEY (supersedes_cash_count_id, business_id)
        REFERENCES operations.cash_counts (id, business_id)
        """
    )
    op.execute(
        """
        ALTER TABLE operations.cash_counts
        ADD CONSTRAINT fk_cash_counts_superseded_by
        FOREIGN KEY (superseded_by_id, business_id)
        REFERENCES operations.cash_counts (id, business_id)
        DEFERRABLE INITIALLY DEFERRED
        """
    )

    op.execute("ALTER TABLE operations.cash_counts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.cash_counts FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.cash_counts
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON operations.cash_counts TO lumo_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS operations.cash_counts")
