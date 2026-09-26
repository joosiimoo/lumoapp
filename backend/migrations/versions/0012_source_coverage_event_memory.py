"""Source coverage and factual event memory.

Revision ID: 0012_source_coverage_event_memory
Revises: 0011_daily_close_outcome
Create Date: 2026-09-25
"""

from __future__ import annotations

from alembic import op

revision = "0012_source_coverage_event_memory"
down_revision = "0011_daily_close_outcome"
branch_labels = None
depends_on = None

_MONEY = r"^-?[0-9]+[.][0-9]{2}$"
_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def upgrade() -> None:
    # Alembic's default version_num is varchar(32). This revision id is longer.
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    op.execute(
        """
        CREATE TABLE operations.source_coverage_records (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operational_day_id UUID NOT NULL,
            domain VARCHAR(32) NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL,
            limitation_code VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_source_coverage_records_identity
                UNIQUE (business_id, operational_day_id, domain, source_type),
            CONSTRAINT ck_source_coverage_records_domain
                CHECK (domain IN ('sales', 'cash_count')),
            CONSTRAINT ck_source_coverage_records_source_type
                CHECK (source_type = 'manual_capture'),
            CONSTRAINT ck_source_coverage_records_status
                CHECK (status = 'observed'),
            CONSTRAINT ck_source_coverage_records_limitation
                CHECK (limitation_code = 'only_lumo_registered_operations'),
            CONSTRAINT fk_source_coverage_records_operational_day
                FOREIGN KEY (operational_day_id, business_id)
                REFERENCES operations.operational_days (id, business_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_source_coverage_records_business_id ON operations.source_coverage_records (business_id)"
    )
    op.execute("ALTER TABLE operations.source_coverage_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.source_coverage_records FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.source_coverage_records
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, DELETE ON operations.source_coverage_records TO lumo_app"
    )
    op.execute(
        f"""
        CREATE TABLE operations.business_events (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operational_day_id UUID NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            source_type VARCHAR(32) NOT NULL,
            source_entity_type VARCHAR(32) NOT NULL,
            source_entity_id UUID NOT NULL,
            facts JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_business_events_source
                UNIQUE (business_id, event_type, source_entity_type, source_entity_id),
            CONSTRAINT ck_business_events_source_type
                CHECK (source_type = 'manual_capture'),
            CONSTRAINT ck_business_events_shape CHECK (
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
            ),
            CONSTRAINT fk_business_events_operational_day
                FOREIGN KEY (operational_day_id, business_id)
                REFERENCES operations.operational_days (id, business_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_business_events_business_day
        ON operations.business_events (business_id, operational_day_id)
        """
    )
    op.execute("ALTER TABLE operations.business_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.business_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.business_events
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON operations.business_events TO lumo_app")
    op.execute(
        """
        CREATE FUNCTION operations.business_events_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            RAISE EXCEPTION 'business events are immutable';
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER business_events_immutable
        BEFORE UPDATE ON operations.business_events
        FOR EACH ROW
        EXECUTE FUNCTION operations.business_events_immutable()
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            coverage_rows integer;
            event_rows integer;
        BEGIN
            ALTER TABLE operations.source_coverage_records DISABLE ROW LEVEL SECURITY;
            ALTER TABLE operations.business_events DISABLE ROW LEVEL SECURITY;
            SELECT count(*)::integer INTO coverage_rows FROM operations.source_coverage_records;
            SELECT count(*)::integer INTO event_rows FROM operations.business_events;
            IF coverage_rows > 0 OR event_rows > 0 THEN
                ALTER TABLE operations.source_coverage_records ENABLE ROW LEVEL SECURITY;
                ALTER TABLE operations.source_coverage_records FORCE ROW LEVEL SECURITY;
                ALTER TABLE operations.business_events ENABLE ROW LEVEL SECURITY;
                ALTER TABLE operations.business_events FORCE ROW LEVEL SECURITY;
                RAISE EXCEPTION
                    'cannot downgrade 0012 while source coverage or a business event exists';
            END IF;
        END
        $fn$;
        """
    )
    op.execute("DROP TABLE operations.business_events")
    op.execute("DROP TABLE operations.source_coverage_records")
    op.execute("DROP FUNCTION operations.business_events_immutable()")
