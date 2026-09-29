"""Onboarding status, payment methods, and actor business links.

Revision ID: 0015_onboarding_minimum_configuration
Revises: 0014_pilot_stage_gate_instrumentation
Create Date: 2026-09-28
"""

from __future__ import annotations

from alembic import op

revision = "0015_onboarding_minimum_configuration"
down_revision = "0014_pilot_stage_gate_instrumentation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE identity.businesses
            ADD COLUMN onboarding_status VARCHAR(32) NOT NULL DEFAULT 'completed',
            ADD COLUMN enabled_payment_methods TEXT[] NULL
        """
    )
    op.execute(
        """
        ALTER TABLE identity.businesses
            ADD CONSTRAINT ck_businesses_onboarding_status
            CHECK (onboarding_status IN ('in_progress', 'completed'))
        """
    )
    op.execute(
        """
        ALTER TABLE identity.businesses
            ADD CONSTRAINT ck_businesses_enabled_payment_methods
            CHECK (
                enabled_payment_methods IS NULL
                OR (
                    cardinality(enabled_payment_methods) >= 1
                    AND enabled_payment_methods <@ ARRAY['cash', 'card', 'transfer']::text[]
                )
            )
        """
    )
    op.execute("ALTER TABLE identity.businesses ALTER COLUMN currency DROP NOT NULL")
    op.execute("ALTER TABLE identity.businesses ALTER COLUMN timezone DROP NOT NULL")
    op.execute(
        """
        CREATE TABLE identity.actor_business_links (
            actor_id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE identity.actor_business_links ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.actor_business_links FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY actor_isolation ON identity.actor_business_links
        USING (actor_id::text = current_setting('app.current_actor_id', true))
        WITH CHECK (actor_id::text = current_setting('app.current_actor_id', true))
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON identity.actor_business_links TO lumo_app"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS identity.actor_business_links")
    op.execute("ALTER TABLE identity.businesses DROP CONSTRAINT IF EXISTS ck_businesses_enabled_payment_methods")
    op.execute("ALTER TABLE identity.businesses DROP CONSTRAINT IF EXISTS ck_businesses_onboarding_status")
    op.execute("ALTER TABLE identity.businesses DROP COLUMN IF EXISTS enabled_payment_methods")
    op.execute("ALTER TABLE identity.businesses DROP COLUMN IF EXISTS onboarding_status")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM identity.businesses WHERE currency IS NULL OR timezone IS NULL) THEN
            RAISE EXCEPTION 'cannot restore NOT NULL while null currency or timezone rows exist';
          END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE identity.businesses ALTER COLUMN currency SET NOT NULL")
    op.execute("ALTER TABLE identity.businesses ALTER COLUMN timezone SET NOT NULL")
