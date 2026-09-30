"""Add optional close_note to closing_snapshots and daily_close facts.

Revision ID: 0017_closing_snapshot_close_note
Revises: 0016_sale_corrections
Create Date: 2026-09-30
"""

from __future__ import annotations

from alembic import op

revision = "0017_closing_snapshot_close_note"
down_revision = "0016_sale_corrections"
branch_labels = None
depends_on = None

_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
_MONEY = r"^-?[0-9]+\.[0-9]{2}$"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        ADD COLUMN IF NOT EXISTS close_note VARCHAR(500) NULL
        """
    )
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
                        - 'cash_difference' - 'cash_status' - 'currency'
                        - 'close_note' = '{{}}'::jsonb
                    AND (
                        NOT (facts ? 'close_note')
                        OR (
                            jsonb_typeof(facts->'close_note') = 'string'
                            AND length(btrim(facts->>'close_note')) > 0
                            AND facts->>'close_note' = btrim(facts->>'close_note')
                            AND length(facts->>'close_note') <= 500
                        )
                    )
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
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        DROP COLUMN IF EXISTS close_note
        """
    )
