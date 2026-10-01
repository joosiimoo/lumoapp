"""Per-business transaction references (TRX) for sale, void, and close.

Revision ID: 0018_transaction_references
Revises: 0017_closing_snapshot_close_note
Create Date: 2026-09-30

Order:
1. counter table + RLS / FORCE RLS
2. nullable sequence columns
3. drop previous business_events exact-shape CHECK
4. deterministic per-business sequence backfill (sale, void, close)
5. enrich historical Event Memory facts (migration-only; events are otherwise immutable)
6. install new exact-shape CHECK requiring TRX keys
7. final CHECKs, unique indexes, NOT NULL on closing_snapshots
8. initialize counters from per-business max

Pre-0018 persisted idempotency response bodies are intentionally not rewritten (ADR-033).
"""

from __future__ import annotations

from alembic import op

revision = "0018_transaction_references"
down_revision = "0017_closing_snapshot_close_note"
branch_labels = None
depends_on = None

_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
_MONEY = r"^-?[0-9]+\.[0-9]{2}$"
_TRX = r"^TRX-[0-9]+$"

# lumo_admin is NOBYPASSRLS. Lift RLS only while this migration backfills every tenant,
# then force it back on before return. A raise rolls the whole migration transaction back.
_RLS_TABLES = (
    "identity.businesses",
    "sales.sale_sessions",
    "operations.closing_snapshots",
    "operations.business_events",
    "operations.business_transaction_counters",
)


def _lift_rls() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


def _restore_rls() -> None:
    for table in _RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


def _trx(expr: str) -> str:
    return f"'TRX-' || lpad(({expr})::text, GREATEST(6, length(({expr})::text)), '0')"


def _shape_check(*, with_trx: bool) -> str:
    """Exact-shape CHECK for business_events.facts (0017 pattern, optionally with TRX keys)."""

    def keys(*names: str) -> str:
        return ", ".join(f"'{name}'" for name in names)

    def minus(*names: str) -> str:
        return " ".join(f"- '{name}'" for name in names)

    sale_keys = ["sale_session_id", "payment_id", "payment_method", "amount", "currency"]
    void_keys = sale_keys + ["void_reason", "voided_by_actor_id"]
    close_keys = [
        "outcome_run_id",
        "closing_snapshot_id",
        "sale_count",
        "gross_sales_total",
        "expected_cash",
        "counted_cash",
        "cash_difference",
        "cash_status",
        "currency",
    ]
    sale_trx = ""
    void_trx = ""
    close_trx = ""
    if with_trx:
        sale_keys = sale_keys + ["transaction_number"]
        void_keys = void_keys + ["transaction_number", "original_transaction_number"]
        close_keys = close_keys + ["transaction_number"]
        sale_trx = f"""
                    AND jsonb_typeof(facts->'transaction_number') = 'string'
                    AND facts->>'transaction_number' ~ '{_TRX}'"""
        void_trx = f"""
                    AND jsonb_typeof(facts->'transaction_number') = 'string'
                    AND facts->>'transaction_number' ~ '{_TRX}'
                    AND jsonb_typeof(facts->'original_transaction_number') = 'string'
                    AND facts->>'original_transaction_number' ~ '{_TRX}'
                    AND facts->>'transaction_number' <> facts->>'original_transaction_number'"""
        close_trx = f"""
                    AND jsonb_typeof(facts->'transaction_number') = 'string'
                    AND facts->>'transaction_number' ~ '{_TRX}'"""

    return f"""
        ALTER TABLE operations.business_events
        ADD CONSTRAINT ck_business_events_shape CHECK (
            jsonb_typeof(facts) = 'object'
            AND (
                (
                    event_type = 'sale_confirmed'
                    AND source_entity_type = 'sale_session'
                    AND facts ?& ARRAY[{keys(*sale_keys)}]::text[]
                    AND facts {minus(*sale_keys)} = '{{}}'::jsonb
                    AND facts->>'sale_session_id' = source_entity_id::text
                    AND facts->>'sale_session_id' ~ '{_UUID}'
                    AND facts->>'payment_id' ~ '{_UUID}'
                    AND jsonb_typeof(facts->'payment_id') = 'string'
                    AND facts->>'payment_method' IN ('cash', 'card', 'transfer')
                    AND jsonb_typeof(facts->'amount') = 'string'
                    AND facts->>'amount' ~ '{_MONEY}'
                    AND jsonb_typeof(facts->'currency') = 'string'
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'{sale_trx}
                )
                OR (
                    event_type = 'sale_voided'
                    AND source_entity_type = 'sale_session'
                    AND facts ?& ARRAY[{keys(*void_keys)}]::text[]
                    AND facts {minus(*void_keys)} = '{{}}'::jsonb
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
                    AND jsonb_typeof(facts->'voided_by_actor_id') = 'string'{void_trx}
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
                    AND facts ?& ARRAY[{keys(*close_keys)}]::text[]
                    AND facts {minus(*close_keys)} - 'close_note' = '{{}}'::jsonb
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
                    AND facts->>'currency' ~ '^[A-Z]{{3}}$'{close_trx}
                )
            )
        )
        """


_CANDIDATES_CTE = """
    WITH candidates AS (
        SELECT
            s.business_id,
            'sale'::text AS kind,
            1 AS type_order,
            s.confirmed_at AS occurred_at,
            s.id AS entity_id
        FROM sales.sale_sessions s
        WHERE s.status IN ('confirmed', 'voided')
          AND s.confirmed_at IS NOT NULL
        UNION ALL
        SELECT s.business_id, 'void'::text, 2, s.voided_at, s.id
        FROM sales.sale_sessions s
        WHERE s.status = 'voided'
          AND s.voided_at IS NOT NULL
        UNION ALL
        SELECT c.business_id, 'close'::text, 3, c.closed_at, c.id
        FROM operations.closing_snapshots c
    ),
    ordered AS (
        SELECT
            business_id,
            kind,
            entity_id,
            ROW_NUMBER() OVER (
                PARTITION BY business_id
                ORDER BY occurred_at ASC, type_order ASC, entity_id ASC
            ) AS seq
        FROM candidates
    )
"""


def upgrade() -> None:
    # 1. Counter table with forced tenant isolation.
    op.execute(
        """
        CREATE TABLE operations.business_transaction_counters (
            business_id UUID PRIMARY KEY
                REFERENCES identity.businesses (id),
            last_value BIGINT NOT NULL DEFAULT 0,
            CONSTRAINT ck_business_transaction_counters_last_value CHECK (last_value >= 0)
        )
        """
    )
    op.execute("ALTER TABLE operations.business_transaction_counters ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.business_transaction_counters FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.business_transaction_counters
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON operations.business_transaction_counters TO lumo_app"
    )

    # 2. Backfill-compatible nullable columns.
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD COLUMN transaction_sequence BIGINT NULL,
        ADD COLUMN void_transaction_sequence BIGINT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        ADD COLUMN transaction_sequence BIGINT NULL
        """
    )

    # 3. The previous exact-shape CHECK would reject enriched facts.
    op.execute("ALTER TABLE operations.business_events DROP CONSTRAINT IF EXISTS ck_business_events_shape")

    _lift_rls()
    op.execute("ALTER TABLE operations.closing_snapshots DISABLE TRIGGER closing_snapshots_immutable")
    op.execute("ALTER TABLE operations.business_events DISABLE TRIGGER business_events_immutable")

    # 4. Deterministic backfill per business: sale@confirmed_at, void@voided_at, close@closed_at.
    op.execute(
        _CANDIDATES_CTE
        + """
        UPDATE sales.sale_sessions AS s
        SET transaction_sequence = o.seq
        FROM ordered o
        WHERE o.kind = 'sale'
          AND s.id = o.entity_id
          AND s.business_id = o.business_id
        """
    )
    op.execute(
        _CANDIDATES_CTE
        + """
        UPDATE sales.sale_sessions AS s
        SET void_transaction_sequence = o.seq
        FROM ordered o
        WHERE o.kind = 'void'
          AND s.id = o.entity_id
          AND s.business_id = o.business_id
        """
    )
    op.execute(
        _CANDIDATES_CTE
        + """
        UPDATE operations.closing_snapshots AS c
        SET transaction_sequence = o.seq
        FROM ordered o
        WHERE o.kind = 'close'
          AND c.id = o.entity_id
          AND c.business_id = o.business_id
        """
    )

    # 5. Migration-only Event Memory enrichment.
    op.execute(
        f"""
        UPDATE operations.business_events AS e
        SET facts = e.facts || jsonb_build_object(
            'transaction_number', {_trx("s.transaction_sequence")}
        )
        FROM sales.sale_sessions AS s
        WHERE e.event_type = 'sale_confirmed'
          AND e.source_entity_type = 'sale_session'
          AND e.source_entity_id = s.id
          AND e.business_id = s.business_id
          AND s.transaction_sequence IS NOT NULL
        """
    )
    op.execute(
        f"""
        UPDATE operations.business_events AS e
        SET facts = e.facts || jsonb_build_object(
            'transaction_number', {_trx("s.void_transaction_sequence")},
            'original_transaction_number', {_trx("s.transaction_sequence")}
        )
        FROM sales.sale_sessions AS s
        WHERE e.event_type = 'sale_voided'
          AND e.source_entity_type = 'sale_session'
          AND e.source_entity_id = s.id
          AND e.business_id = s.business_id
          AND s.transaction_sequence IS NOT NULL
          AND s.void_transaction_sequence IS NOT NULL
        """
    )
    op.execute(
        f"""
        UPDATE operations.business_events AS e
        SET facts = e.facts || jsonb_build_object(
            'transaction_number', {_trx("c.transaction_sequence")}
        )
        FROM operations.closing_snapshots AS c
        WHERE e.event_type = 'daily_close_completed'
          AND e.source_entity_type = 'closing_snapshot'
          AND e.source_entity_id = c.id
          AND e.business_id = c.business_id
          AND c.transaction_sequence IS NOT NULL
        """
    )

    # 6. New exact-shape CHECK (cash_count_recorded unchanged).
    op.execute(_shape_check(with_trx=True))

    # 7. Final constraints.
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_transaction_sequences CHECK (
            (
                status IN ('confirmed', 'voided')
                AND transaction_sequence IS NOT NULL
                AND transaction_sequence >= 1
            )
            OR (
                status IN ('open', 'ready_to_charge')
                AND transaction_sequence IS NULL
            )
        )
        """
    )
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_void_transaction_sequence CHECK (
            (
                status = 'voided'
                AND void_transaction_sequence IS NOT NULL
                AND void_transaction_sequence >= 1
                AND void_transaction_sequence <> transaction_sequence
            )
            OR (
                status <> 'voided'
                AND void_transaction_sequence IS NULL
            )
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sale_sessions_business_transaction_sequence
        ON sales.sale_sessions (business_id, transaction_sequence)
        WHERE transaction_sequence IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sale_sessions_business_void_transaction_sequence
        ON sales.sale_sessions (business_id, void_transaction_sequence)
        WHERE void_transaction_sequence IS NOT NULL
        """
    )
    # Every pre-0018 snapshot was backfilled in step 4 before NOT NULL.
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        ALTER COLUMN transaction_sequence SET NOT NULL
        """
    )
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        ADD CONSTRAINT ck_closing_snapshots_transaction_sequence CHECK (transaction_sequence >= 1)
        """
    )
    op.execute(
        """
        ALTER TABLE operations.closing_snapshots
        ADD CONSTRAINT uq_closing_snapshots_business_transaction_sequence
        UNIQUE (business_id, transaction_sequence)
        """
    )

    # 8. Counters: one row per business, last_value from the maximum assigned sequence.
    op.execute(
        """
        INSERT INTO operations.business_transaction_counters (business_id, last_value)
        SELECT id, 0 FROM identity.businesses
        ON CONFLICT DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE operations.business_transaction_counters AS c
        SET last_value = m.max_seq
        FROM (
            SELECT business_id, MAX(seq) AS max_seq
            FROM (
                SELECT business_id, transaction_sequence AS seq FROM sales.sale_sessions
                UNION ALL
                SELECT business_id, void_transaction_sequence FROM sales.sale_sessions
                UNION ALL
                SELECT business_id, transaction_sequence FROM operations.closing_snapshots
            ) AS all_seq
            WHERE seq IS NOT NULL
            GROUP BY business_id
        ) AS m
        WHERE c.business_id = m.business_id
        """
    )

    op.execute("ALTER TABLE operations.business_events ENABLE TRIGGER business_events_immutable")
    op.execute("ALTER TABLE operations.closing_snapshots ENABLE TRIGGER closing_snapshots_immutable")
    _restore_rls()


def downgrade() -> None:
    op.execute("ALTER TABLE operations.business_events DROP CONSTRAINT IF EXISTS ck_business_events_shape")
    _lift_rls()
    op.execute("ALTER TABLE operations.business_events DISABLE TRIGGER business_events_immutable")

    # Strip enriched facts so the restored 0017 exact-shape CHECK holds.
    op.execute(
        """
        UPDATE operations.business_events
        SET facts = facts - 'transaction_number' - 'original_transaction_number'
        WHERE event_type IN ('sale_confirmed', 'sale_voided', 'daily_close_completed')
        """
    )
    op.execute(_shape_check(with_trx=False))
    op.execute("ALTER TABLE operations.business_events ENABLE TRIGGER business_events_immutable")

    op.execute(
        "ALTER TABLE operations.closing_snapshots "
        "DROP CONSTRAINT IF EXISTS uq_closing_snapshots_business_transaction_sequence"
    )
    op.execute(
        "ALTER TABLE operations.closing_snapshots "
        "DROP CONSTRAINT IF EXISTS ck_closing_snapshots_transaction_sequence"
    )
    op.execute("ALTER TABLE operations.closing_snapshots DROP COLUMN IF EXISTS transaction_sequence")
    op.execute("DROP INDEX IF EXISTS sales.uq_sale_sessions_business_void_transaction_sequence")
    op.execute("DROP INDEX IF EXISTS sales.uq_sale_sessions_business_transaction_sequence")
    op.execute(
        "ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_void_transaction_sequence"
    )
    op.execute(
        "ALTER TABLE sales.sale_sessions DROP CONSTRAINT IF EXISTS ck_sale_sessions_transaction_sequences"
    )
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS void_transaction_sequence")
    op.execute("ALTER TABLE sales.sale_sessions DROP COLUMN IF EXISTS transaction_sequence")
    op.execute("DROP TABLE IF EXISTS operations.business_transaction_counters")

    for table in _RLS_TABLES[:-1]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
