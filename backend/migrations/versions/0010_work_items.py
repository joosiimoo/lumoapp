"""Daily Close WorkItems.

Revision ID: 0010_work_items
Revises: 0009_catalog_price_override
Create Date: 2026-09-24
"""

from __future__ import annotations

from alembic import op

revision = "0010_work_items"
down_revision = "0009_catalog_price_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE operations.work_items (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operational_day_id UUID NOT NULL,
            type VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL,
            priority VARCHAR(16) NOT NULL,
            responsible_party VARCHAR(32) NOT NULL,
            reason_code VARCHAR(64) NOT NULL,
            source VARCHAR(64) NOT NULL,
            evidence JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            resolved_at TIMESTAMPTZ NULL,
            resolution_actor_type VARCHAR(16) NULL,
            resolved_by_actor_id UUID NULL,
            resolution_code VARCHAR(64) NULL,
            CONSTRAINT ck_work_items_type CHECK (
                type IN (
                    'cash_count_required',
                    'cash_difference_review',
                    'close_confirmation_required'
                )
            ),
            CONSTRAINT ck_work_items_status CHECK (status IN ('open', 'resolved')),
            CONSTRAINT ck_work_items_responsible_party CHECK (responsible_party = 'business'),
            CONSTRAINT ck_work_items_source CHECK (source = 'daily_close_rule'),
            CONSTRAINT ck_work_items_evidence_object CHECK (jsonb_typeof(evidence) = 'object'),
            CONSTRAINT ck_work_items_type_priority_reason CHECK (
                (
                    type = 'cash_count_required'
                    AND priority = 'critical'
                    AND reason_code = 'cash_count_missing'
                )
                OR (
                    type = 'cash_difference_review'
                    AND priority = 'high'
                    AND reason_code IN ('cash_short', 'cash_over')
                )
                OR (
                    type = 'close_confirmation_required'
                    AND priority = 'normal'
                    AND reason_code = 'close_confirmation_required'
                )
            ),
            CONSTRAINT ck_work_items_resolution_actor_type CHECK (
                resolution_actor_type IS NULL
                OR resolution_actor_type IN ('business', 'system')
            ),
            CONSTRAINT ck_work_items_resolution_code CHECK (
                resolution_code IS NULL
                OR resolution_code IN (
                    'cash_count_recorded',
                    'cash_balanced',
                    'day_closed',
                    'cash_unbalanced'
                )
            ),
            CONSTRAINT ck_work_items_resolution CHECK (
                (
                    status = 'open'
                    AND resolved_at IS NULL
                    AND resolution_actor_type IS NULL
                    AND resolved_by_actor_id IS NULL
                    AND resolution_code IS NULL
                )
                OR (
                    status = 'resolved'
                    AND resolution_actor_type = 'business'
                    AND resolved_at IS NOT NULL
                    AND resolved_by_actor_id IS NOT NULL
                    AND resolution_code IS NOT NULL
                )
                OR (
                    status = 'resolved'
                    AND resolution_actor_type = 'system'
                    AND resolved_at IS NOT NULL
                    AND resolved_by_actor_id IS NULL
                    AND resolution_code IS NOT NULL
                )
            ),
            CONSTRAINT fk_work_items_operational_day
                FOREIGN KEY (operational_day_id, business_id)
                REFERENCES operations.operational_days (id, business_id)
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_work_items_one_open
        ON operations.work_items (business_id, operational_day_id, type)
        WHERE status = 'open'
        """
    )
    op.execute("CREATE INDEX ix_work_items_business_id ON operations.work_items (business_id)")
    op.execute("ALTER TABLE operations.work_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.work_items FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.work_items
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operations.work_items TO lumo_app"
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            item_rows integer;
        BEGIN
            ALTER TABLE operations.work_items DISABLE ROW LEVEL SECURITY;
            SELECT count(*)::integer INTO item_rows FROM operations.work_items;
            IF item_rows > 0 THEN
                ALTER TABLE operations.work_items ENABLE ROW LEVEL SECURITY;
                ALTER TABLE operations.work_items FORCE ROW LEVEL SECURITY;
                RAISE EXCEPTION 'cannot downgrade 0010 while a work item exists';
            END IF;
        END
        $fn$;
        """
    )
    op.execute("DROP TABLE operations.work_items")
