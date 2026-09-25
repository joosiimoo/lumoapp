"""Daily Close OutcomeRun.

Revision ID: 0011_daily_close_outcome
Revises: 0010_work_items
Create Date: 2026-09-24
"""

from __future__ import annotations

from alembic import op

revision = "0011_daily_close_outcome"
down_revision = "0010_work_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        ADD CONSTRAINT uq_closing_snapshots_id_business_day
        UNIQUE (id, business_id, operational_day_id)
        """
    )
    op.execute(
        """
        CREATE TABLE operations.outcome_runs (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operational_day_id UUID NOT NULL,
            outcome_type VARCHAR(64) NOT NULL,
            outcome_version INTEGER NOT NULL,
            status VARCHAR(16) NOT NULL,
            owner_type VARCHAR(32) NOT NULL,
            reason_code VARCHAR(64) NOT NULL,
            evidence JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            ready_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL,
            closing_snapshot_id UUID NULL,
            CONSTRAINT uq_outcome_runs_id_business UNIQUE (id, business_id),
            CONSTRAINT uq_outcome_runs_id_business_day UNIQUE (id, business_id, operational_day_id),
            CONSTRAINT uq_outcome_runs_identity
                UNIQUE (business_id, operational_day_id, outcome_type, outcome_version),
            CONSTRAINT ck_outcome_runs_type CHECK (outcome_type = 'daily_close_ready'),
            CONSTRAINT ck_outcome_runs_version CHECK (outcome_version = 1),
            CONSTRAINT ck_outcome_runs_owner CHECK (owner_type = 'business'),
            CONSTRAINT ck_outcome_runs_status CHECK (status IN ('in_progress', 'ready', 'completed')),
            CONSTRAINT ck_outcome_runs_reason CHECK (
                reason_code IN (
                    'awaiting_cash_count',
                    'ready_balanced',
                    'ready_cash_short',
                    'ready_cash_over',
                    'closed_confirmed'
                )
            ),
            CONSTRAINT ck_outcome_runs_evidence_object CHECK (jsonb_typeof(evidence) = 'object'),
            CONSTRAINT ck_outcome_runs_state CHECK (
                (
                    status = 'in_progress'
                    AND reason_code = 'awaiting_cash_count'
                    AND ready_at IS NULL
                    AND completed_at IS NULL
                    AND closing_snapshot_id IS NULL
                    AND evidence->>'cash_status' = 'not_counted'
                    AND NOT (evidence ? 'current_cash_count_id')
                )
                OR (
                    status = 'ready'
                    AND ready_at IS NOT NULL
                    AND completed_at IS NULL
                    AND closing_snapshot_id IS NULL
                    AND (
                        (reason_code = 'ready_balanced' AND evidence->>'cash_status' = 'balanced')
                        OR (reason_code = 'ready_cash_short' AND evidence->>'cash_status' = 'short')
                        OR (reason_code = 'ready_cash_over' AND evidence->>'cash_status' = 'over')
                    )
                    AND evidence ? 'current_cash_count_id'
                )
                OR (
                    status = 'completed'
                    AND reason_code = 'closed_confirmed'
                    AND ready_at IS NOT NULL
                    AND completed_at IS NOT NULL
                    AND closing_snapshot_id IS NOT NULL
                    AND evidence->>'cash_status' IN ('balanced', 'short', 'over')
                    AND evidence ? 'current_cash_count_id'
                )
            ),
            CONSTRAINT fk_outcome_runs_operational_day
                FOREIGN KEY (operational_day_id, business_id)
                REFERENCES operations.operational_days (id, business_id),
            CONSTRAINT fk_outcome_runs_closing_snapshot
                FOREIGN KEY (closing_snapshot_id, business_id, operational_day_id)
                REFERENCES operations.closing_snapshots (id, business_id, operational_day_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_outcome_runs_business_id ON operations.outcome_runs (business_id)")
    op.execute("ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.outcome_runs
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON operations.outcome_runs TO lumo_app")
    op.execute("ALTER TABLE operations.work_items ADD COLUMN outcome_run_id UUID NULL")
    op.execute(
        """
        ALTER TABLE operations.work_items
        ADD CONSTRAINT fk_work_items_outcome_run
        FOREIGN KEY (outcome_run_id, business_id, operational_day_id)
        REFERENCES operations.outcome_runs (id, business_id, operational_day_id)
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            outcome_rows integer;
        BEGIN
            ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY;
            SELECT count(*)::integer INTO outcome_rows FROM operations.outcome_runs;
            IF outcome_rows > 0 THEN
                ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY;
                ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY;
                RAISE EXCEPTION 'cannot downgrade 0011 while an outcome run exists';
            END IF;
        END
        $fn$;
        """
    )
    op.execute("ALTER TABLE operations.work_items DROP CONSTRAINT fk_work_items_outcome_run")
    op.execute("ALTER TABLE operations.work_items DROP COLUMN outcome_run_id")
    op.execute("DROP TABLE operations.outcome_runs")
    op.execute(
        "ALTER TABLE operations.closing_snapshots DROP CONSTRAINT uq_closing_snapshots_id_business_day"
    )
