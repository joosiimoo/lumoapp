"""Daily close confirmation and immutable closing snapshots.

Revision ID: 0007_daily_close_confirmation
Revises: 0006_cash_count
Create Date: 2026-09-22
"""

from __future__ import annotations

from alembic import op

revision = "0007_daily_close_confirmation"
down_revision = "0006_cash_count"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE operations.operational_days DROP CONSTRAINT ck_operational_days_status")
    op.execute(
        """
        ALTER TABLE operations.operational_days
        ADD CONSTRAINT ck_operational_days_status CHECK (status IN ('open', 'closed'))
        """
    )
    op.execute(
        """
        ALTER TABLE operations.cash_counts
        ADD CONSTRAINT uq_cash_counts_id_business_day
        UNIQUE (id, business_id, operational_day_id)
        """
    )
    op.execute(
        """
        CREATE TABLE operations.closing_snapshots (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operational_day_id UUID NOT NULL,
            cash_count_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            business_date DATE NOT NULL,
            currency VARCHAR(3) NOT NULL,
            sale_count INTEGER NOT NULL,
            gross_sales_total NUMERIC(12, 2) NOT NULL,
            cash_total NUMERIC(12, 2) NOT NULL,
            card_total NUMERIC(12, 2) NOT NULL,
            transfer_total NUMERIC(12, 2) NOT NULL,
            expected_cash NUMERIC(12, 2) NOT NULL,
            counted_cash NUMERIC(12, 2) NOT NULL,
            cash_difference NUMERIC(12, 2) NOT NULL,
            cash_status VARCHAR(16) NOT NULL,
            closed_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_closing_snapshots_sale_count CHECK (sale_count >= 0),
            CONSTRAINT ck_closing_snapshots_money_non_negative CHECK (
                gross_sales_total >= 0
                AND cash_total >= 0
                AND card_total >= 0
                AND transfer_total >= 0
                AND expected_cash >= 0
                AND counted_cash >= 0
            ),
            CONSTRAINT ck_closing_snapshots_expected_is_cash CHECK (expected_cash = cash_total),
            CONSTRAINT ck_closing_snapshots_gross CHECK (
                gross_sales_total = cash_total + card_total + transfer_total
            ),
            CONSTRAINT ck_closing_snapshots_difference CHECK (
                cash_difference = counted_cash - expected_cash
            ),
            CONSTRAINT ck_closing_snapshots_cash_status CHECK (
                (cash_difference > 0 AND cash_status = 'over')
                OR (cash_difference < 0 AND cash_status = 'short')
                OR (cash_difference = 0 AND cash_status = 'balanced')
            ),
            CONSTRAINT uq_closing_snapshots_operational_day UNIQUE (operational_day_id),
            CONSTRAINT uq_closing_snapshots_id_business UNIQUE (id, business_id),
            CONSTRAINT uq_closing_snapshots_cash_count UNIQUE (cash_count_id),
            CONSTRAINT fk_closing_snapshots_operational_day
                FOREIGN KEY (operational_day_id, business_id)
                REFERENCES operations.operational_days (id, business_id),
            CONSTRAINT fk_closing_snapshots_cash_count
                FOREIGN KEY (cash_count_id, business_id, operational_day_id)
                REFERENCES operations.cash_counts (id, business_id, operational_day_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_closing_snapshots_business_id ON operations.closing_snapshots (business_id)")
    op.execute("ALTER TABLE operations.closing_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE operations.closing_snapshots FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON operations.closing_snapshots
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, DELETE ON operations.closing_snapshots TO lumo_app"
    )
    op.execute(
        """
        CREATE FUNCTION operations.closing_snapshots_immutable()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            RAISE EXCEPTION 'closing snapshots are immutable';
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER closing_snapshots_immutable
        BEFORE UPDATE ON operations.closing_snapshots
        FOR EACH ROW
        EXECUTE FUNCTION operations.closing_snapshots_immutable()
        """
    )
    # SECURITY DEFINER stabilizes the owner and search_path. It does not bypass FORCE RLS:
    # the owner is a non-superuser without BYPASSRLS. The function sets the tenant GUC from
    # the trigger row, queries only that pair, and restores the caller value.
    op.execute(
        """
        CREATE FUNCTION operations.assert_closing_snapshot_cardinality()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = operations, pg_temp
        AS $fn$
        DECLARE
            target_day_id uuid;
            target_business_id uuid;
            saved_tenant text;
            day_status text;
            snapshot_count integer;
            day_exists boolean;
        BEGIN
            IF TG_TABLE_NAME = 'closing_snapshots' THEN
                IF TG_OP = 'DELETE' THEN
                    target_day_id := OLD.operational_day_id;
                    target_business_id := OLD.business_id;
                ELSE
                    target_day_id := NEW.operational_day_id;
                    target_business_id := NEW.business_id;
                END IF;
            ELSE
                IF TG_OP = 'DELETE' THEN
                    target_day_id := OLD.id;
                    target_business_id := OLD.business_id;
                ELSE
                    target_day_id := NEW.id;
                    target_business_id := NEW.business_id;
                END IF;
            END IF;

            saved_tenant := current_setting('app.current_business_id', true);

            BEGIN
                PERFORM set_config('app.current_business_id', target_business_id::text, true);

                SELECT EXISTS (
                    SELECT 1
                    FROM operational_days
                    WHERE id = target_day_id
                      AND business_id = target_business_id
                ) INTO day_exists;

                day_status := NULL;
                IF day_exists THEN
                    SELECT status INTO day_status
                    FROM operational_days
                    WHERE id = target_day_id
                      AND business_id = target_business_id;
                END IF;

                SELECT count(*)::integer INTO snapshot_count
                FROM closing_snapshots
                WHERE operational_day_id = target_day_id
                  AND business_id = target_business_id;

                IF NOT day_exists THEN
                    IF snapshot_count <> 0 THEN
                        RAISE EXCEPTION 'closing snapshot cardinality: snapshot without operational day';
                    END IF;
                ELSIF day_status = 'open' THEN
                    IF snapshot_count <> 0 THEN
                        RAISE EXCEPTION 'closing snapshot cardinality: open day must have zero snapshots';
                    END IF;
                ELSIF day_status = 'closed' THEN
                    IF snapshot_count <> 1 THEN
                        RAISE EXCEPTION 'closing snapshot cardinality: closed day must have exactly one snapshot';
                    END IF;
                ELSE
                    RAISE EXCEPTION 'closing snapshot cardinality: illegal operational day status';
                END IF;

                PERFORM operations.restore_closing_snapshot_tenant(saved_tenant);
                RETURN NULL;
            EXCEPTION
                WHEN OTHERS THEN
                    PERFORM operations.restore_closing_snapshot_tenant(saved_tenant);
                    RAISE;
            END;
        END;
        $fn$
        """
    )
    # Restore is a separate function so both the success path and the exception path share
    # one implementation. It is not SECURITY DEFINER and it does not query tenant tables.
    # A NULL save means the GUC was never initialized. SET LOCAL ... TO DEFAULT is the
    # approved restore. On PostgreSQL 16.14 that leaves '', which matches no business UUID.
    # A non-empty saved value is restored exactly with set_config.
    op.execute(
        """
        CREATE FUNCTION operations.restore_closing_snapshot_tenant(saved_tenant text)
        RETURNS void
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF saved_tenant IS NULL THEN
                SET LOCAL app.current_business_id TO DEFAULT;
            ELSE
                PERFORM set_config('app.current_business_id', saved_tenant, true);
            END IF;
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER closing_snapshots_match_day
        AFTER INSERT OR DELETE ON operations.closing_snapshots
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION operations.assert_closing_snapshot_cardinality()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER operational_days_match_snapshot
        AFTER INSERT OR DELETE OR UPDATE OF status ON operations.operational_days
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION operations.assert_closing_snapshot_cardinality()
        """
    )


def downgrade() -> None:
    # lumo_admin is NOBYPASSRLS. Lift RLS only inside this block so the abort check sees every
    # tenant, then force it back on before deciding. A raise rolls the block back with the
    # migration transaction.
    op.execute(
        """
        DO $fn$
        DECLARE
            closed_days integer;
            snapshots integer;
        BEGIN
            ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY;
            ALTER TABLE operations.closing_snapshots DISABLE ROW LEVEL SECURITY;
            SELECT count(*)::integer INTO closed_days
            FROM operations.operational_days
            WHERE status = 'closed';
            SELECT count(*)::integer INTO snapshots
            FROM operations.closing_snapshots;
            ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY;
            ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY;
            ALTER TABLE operations.closing_snapshots ENABLE ROW LEVEL SECURITY;
            ALTER TABLE operations.closing_snapshots FORCE ROW LEVEL SECURITY;
            IF closed_days > 0 OR snapshots > 0 THEN
                RAISE EXCEPTION 'cannot downgrade 0007 while a confirmed close exists';
            END IF;
        END;
        $fn$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS closing_snapshots_immutable ON operations.closing_snapshots")
    op.execute("DROP TRIGGER IF EXISTS closing_snapshots_match_day ON operations.closing_snapshots")
    op.execute("DROP TRIGGER IF EXISTS operational_days_match_snapshot ON operations.operational_days")
    op.execute("DROP FUNCTION IF EXISTS operations.assert_closing_snapshot_cardinality()")
    op.execute("DROP FUNCTION IF EXISTS operations.restore_closing_snapshot_tenant(text)")
    op.execute("DROP FUNCTION IF EXISTS operations.closing_snapshots_immutable()")
    op.execute("DROP TABLE IF EXISTS operations.closing_snapshots")
    op.execute(
        "ALTER TABLE operations.cash_counts DROP CONSTRAINT IF EXISTS uq_cash_counts_id_business_day"
    )
    op.execute("ALTER TABLE operations.operational_days DROP CONSTRAINT ck_operational_days_status")
    op.execute(
        """
        ALTER TABLE operations.operational_days
        ADD CONSTRAINT ck_operational_days_status CHECK (status IN ('open'))
        """
    )
