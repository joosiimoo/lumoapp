"""Sale corrections: voided status, void metadata, sale_revision, sale_voided memory.

Revision ID: 0016_sale_corrections
Revises: 0015_onboarding_minimum_configuration
Create Date: 2026-09-29
"""

from __future__ import annotations

from alembic import op

revision = "0016_sale_corrections"
down_revision = "0015_onboarding_minimum_configuration"
branch_labels = None
depends_on = None

_MONEY = r"^-?[0-9]+[.][0-9]{2}$"
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD COLUMN sale_revision INTEGER NOT NULL DEFAULT 1
        """
    )
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_sale_revision
        CHECK (sale_revision >= 1)
        """
    )
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD COLUMN voided_at TIMESTAMPTZ NULL,
        ADD COLUMN voided_by_actor_id UUID NULL,
        ADD COLUMN void_reason VARCHAR(500) NULL
        """
    )

    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT ck_sale_sessions_status")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_status
        CHECK (status IN ('open', 'ready_to_charge', 'confirmed', 'voided'))
        """
    )

    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT ck_sale_sessions_day_membership")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_day_membership
        CHECK (
            (
                status IN ('confirmed', 'voided')
                AND operational_day_id IS NOT NULL
                AND confirmed_at IS NOT NULL
            )
            OR (
                status IN ('open', 'ready_to_charge')
                AND operational_day_id IS NULL
                AND confirmed_at IS NULL
            )
        )
        """
    )

    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_void_metadata
        CHECK (
            (
                status = 'voided'
                AND voided_at IS NOT NULL
                AND voided_by_actor_id IS NOT NULL
                AND void_reason IS NOT NULL
                AND length(btrim(void_reason)) > 0
                AND void_reason = btrim(void_reason)
            )
            OR (
                status <> 'voided'
                AND voided_at IS NULL
                AND voided_by_actor_id IS NULL
                AND void_reason IS NULL
            )
        )
        """
    )

    # Extend Event Memory shape to allow sale_voided alongside sale_confirmed.
    op.execute("ALTER TABLE operations.business_events DROP CONSTRAINT ck_business_events_shape")
    op.execute(
        f"""
        ALTER TABLE operations.business_events
        ADD CONSTRAINT ck_business_events_shape CHECK (
            jsonb_typeof(facts) = 'object'
            AND (
                (
                    event_type = 'sale_confirmed'
                    AND source_entity_type = 'sale_session'
                    AND facts ?& ARRAY[
                        'sale_session_id', 'payment_id', 'payment_method', 'amount', 'currency'
                    ]::text[]
                    AND facts - 'sale_session_id' - 'payment_id' - 'payment_method'
                        - 'amount' - 'currency' = '{{}}'::jsonb
                    AND facts->>'sale_session_id' = source_entity_id::text
                    AND facts->>'sale_session_id' ~ '{_UUID}'
                    AND facts->>'payment_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'payment_id') = 'string'
                    AND facts->>'payment_method' IN ('cash', 'card', 'transfer')
                    AND jsonb_typeof(facts->'amount') = 'string'
                    AND facts->>'amount' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                )
                OR (
                    event_type = 'sale_voided'
                    AND source_entity_type = 'sale_session'
                    AND facts ?& ARRAY[
                        'sale_session_id', 'payment_id', 'payment_method', 'amount', 'currency',
                        'void_reason', 'voided_by_actor_id'
                    ]::text[]
                    AND facts - 'sale_session_id' - 'payment_id' - 'payment_method'
                        - 'amount' - 'currency' - 'void_reason' - 'voided_by_actor_id'
                        = '{{}}'::jsonb
                    AND facts->>'sale_session_id' = source_entity_id::text
                    AND facts->>'sale_session_id' ~ '{_UUID}'
                    AND facts->>'payment_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'payment_id') = 'string'
                    AND facts->>'payment_method' IN ('cash', 'card', 'transfer')
                    AND jsonb_typeof(facts->'amount') = 'string'
                    AND facts->>'amount' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                    AND jsonb_typeof(facts->'void_reason') = 'string'
                    AND length(btrim(facts->>'void_reason')) > 0
                    AND facts->>'void_reason' = btrim(facts->>'void_reason')
                    AND facts->>'voided_by_actor_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'voided_by_actor_id') = 'string'
                )
                OR (
                    event_type = 'cash_count_recorded'
                    AND source_entity_type = 'cash_count'
                    AND facts ?& ARRAY[
                        'cash_count_id', 'expected_cash', 'counted_cash',
                        'cash_difference', 'cash_status', 'currency'
                    ]::text[]
                    AND facts - 'cash_count_id' - 'expected_cash' - 'counted_cash'
                        - 'cash_difference' - 'cash_status' - 'currency' = '{{}}'::jsonb
                    AND facts->>'cash_count_id' = source_entity_id::text
                    AND facts->>'cash_count_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'expected_cash') = 'string'
                    AND facts->>'expected_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'counted_cash') = 'string'
                    AND facts->>'counted_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'cash_difference') = 'string'
                    AND facts->>'cash_difference' ~ '{_MONEY}'
                    AND facts->>'cash_status' IN ('balanced', 'short', 'over')
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                )
                OR (
                    event_type = 'daily_close_completed'
                    AND source_entity_type = 'closing_snapshot'
                    AND facts ?& ARRAY[
                        'outcome_run_id', 'closing_snapshot_id', 'sale_count',
                        'gross_sales_total', 'expected_cash', 'counted_cash',
                        'cash_difference', 'cash_status', 'currency'
                    ]::text[]
                    AND facts - 'outcome_run_id' - 'closing_snapshot_id' - 'sale_count'
                        - 'gross_sales_total' - 'expected_cash' - 'counted_cash'
                        - 'cash_difference' - 'cash_status' - 'currency' = '{{}}'::jsonb
                    AND facts->>'closing_snapshot_id' = source_entity_id::text
                    AND facts->>'closing_snapshot_id' ~ '{_UUID}'
                    AND facts->>'outcome_run_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'outcome_run_id') = 'string'
                    AND jsonb_typeof(facts->'sale_count') = 'number'
                    AND facts->>'sale_count' ~ '^[0-9]+$'
                    AND jsonb_typeof(facts->'gross_sales_total') = 'string'
                    AND facts->>'gross_sales_total' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'expected_cash') = 'string'
                    AND facts->>'expected_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'counted_cash') = 'string'
                    AND facts->>'counted_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'cash_difference') = 'string'
                    AND facts->>'cash_difference' ~ '{_MONEY}'
                    AND facts->>'cash_status' IN ('balanced', 'short', 'over')
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                )
            )
        )
        """
    )


def downgrade() -> None:
    # Refuse reverse deploy when any voided row or sale_voided memory exists.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM sales.sale_sessions WHERE status = 'voided' LIMIT 1
            ) THEN
                RAISE EXCEPTION 'cannot downgrade 0016_sale_corrections while voided sessions exist';
            END IF;
            IF EXISTS (
                SELECT 1 FROM operations.business_events
                WHERE event_type = 'sale_voided' LIMIT 1
            ) THEN
                RAISE EXCEPTION 'cannot downgrade 0016_sale_corrections while sale_voided events exist';
            END IF;
        END $$;
        """
    )
    # Restore prior Event Memory shape (sale_confirmed / cash_count / daily_close only).
    op.execute("ALTER TABLE operations.business_events DROP CONSTRAINT IF EXISTS ck_business_events_shape")
    op.execute(
        f"""
        ALTER TABLE operations.business_events
        ADD CONSTRAINT ck_business_events_shape CHECK (
            jsonb_typeof(facts) = 'object'
            AND (
                (
                    event_type = 'sale_confirmed'
                    AND source_entity_type = 'sale_session'
                    AND facts ?& ARRAY[
                        'sale_session_id', 'payment_id', 'payment_method', 'amount', 'currency'
                    ]::text[]
                    AND facts - 'sale_session_id' - 'payment_id' - 'payment_method'
                        - 'amount' - 'currency' = '{{}}'::jsonb
                    AND facts->>'sale_session_id' = source_entity_id::text
                    AND facts->>'sale_session_id' ~ '{_UUID}'
                    AND facts->>'payment_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'payment_id') = 'string'
                    AND facts->>'payment_method' IN ('cash', 'card', 'transfer')
                    AND jsonb_typeof(facts->'amount') = 'string'
                    AND facts->>'amount' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                )
                OR (
                    event_type = 'cash_count_recorded'
                    AND source_entity_type = 'cash_count'
                    AND facts ?& ARRAY[
                        'cash_count_id', 'expected_cash', 'counted_cash',
                        'cash_difference', 'cash_status', 'currency'
                    ]::text[]
                    AND facts - 'cash_count_id' - 'expected_cash' - 'counted_cash'
                        - 'cash_difference' - 'cash_status' - 'currency' = '{{}}'::jsonb
                    AND facts->>'cash_count_id' = source_entity_id::text
                    AND facts->>'cash_count_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'expected_cash') = 'string'
                    AND facts->>'expected_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'counted_cash') = 'string'
                    AND facts->>'counted_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'cash_difference') = 'string'
                    AND facts->>'cash_difference' ~ '{_MONEY}'
                    AND facts->>'cash_status' IN ('balanced', 'short', 'over')
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                )
                OR (
                    event_type = 'daily_close_completed'
                    AND source_entity_type = 'closing_snapshot'
                    AND facts ?& ARRAY[
                        'outcome_run_id', 'closing_snapshot_id', 'sale_count',
                        'gross_sales_total', 'expected_cash', 'counted_cash',
                        'cash_difference', 'cash_status', 'currency'
                    ]::text[]
                    AND facts - 'outcome_run_id' - 'closing_snapshot_id' - 'sale_count'
                        - 'gross_sales_total' - 'expected_cash' - 'counted_cash'
                        - 'cash_difference' - 'cash_status' - 'currency' = '{{}}'::jsonb
                    AND facts->>'closing_snapshot_id' = source_entity_id::text
                    AND facts->>'closing_snapshot_id' ~ '{_UUID}'
                    AND facts->>'outcome_run_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'outcome_run_id') = 'string'
                    AND jsonb_typeof(facts->'sale_count') = 'number'
                    AND facts->>'sale_count' ~ '^[0-9]+$'
                    AND jsonb_typeof(facts->'gross_sales_total') = 'string'
                    AND facts->>'gross_sales_total' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'expected_cash') = 'string'
                    AND facts->>'expected_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'counted_cash') = 'string'
                    AND facts->>'counted_cash' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'cash_difference') = 'string'
                    AND facts->>'cash_difference' ~ '{_MONEY}'
                    AND facts->>'cash_status' IN ('balanced', 'short', 'over')
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'
                )
            )
        )
        """
    )
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_void_metadata")
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_day_membership")
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
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_status")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_status
        CHECK (status IN ('open', 'ready_to_charge', 'confirmed'))
        """
    )
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS void_reason")
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS voided_by_actor_id")
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS voided_at")
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_sale_revision")
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS sale_revision")
