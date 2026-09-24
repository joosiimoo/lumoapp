"""Catalog price snapshot and override reason on sale items.

Revision ID: 0009_catalog_price_override
Revises: 0008_noncatalog_sale_item
Create Date: 2026-09-23
"""

from __future__ import annotations

from alembic import op

revision = "0009_catalog_price_override"
down_revision = "0008_noncatalog_sale_item"
branch_labels = None
depends_on = None

_CATALOG_PRICE_CHECK = """
(
    source_type = 'catalog'
    AND product_id IS NOT NULL
    AND catalog_unit_price_snapshot IS NOT NULL
    AND catalog_unit_price_snapshot > 0
    AND unit_price = catalog_unit_price_snapshot
    AND price_override_reason IS NULL
)
OR (
    source_type = 'catalog'
    AND product_id IS NOT NULL
    AND catalog_unit_price_snapshot IS NOT NULL
    AND catalog_unit_price_snapshot > 0
    AND unit_price <> catalog_unit_price_snapshot
    AND price_override_reason IS NOT NULL
    AND length(btrim(price_override_reason)) > 0
    AND price_override_reason = btrim(price_override_reason)
)
OR (
    source_type = 'free_concept'
    AND product_id IS NULL
    AND catalog_unit_price_snapshot IS NULL
    AND price_override_reason IS NULL
)
"""


def upgrade() -> None:
    # lumo_admin is NOBYPASSRLS. Lift RLS only while this migration backfills
    # every tenant, then force it back on before return, including on failure.
    op.execute(
        f"""
        DO $fn$
        BEGIN
            ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY;

            ALTER TABLE sales.sale_items
            ADD COLUMN catalog_unit_price_snapshot NUMERIC(12, 2);
            ALTER TABLE sales.sale_items
            ADD COLUMN price_override_reason VARCHAR(200);

            UPDATE sales.sale_items
            SET catalog_unit_price_snapshot = unit_price,
                price_override_reason = NULL
            WHERE source_type = 'catalog';

            UPDATE sales.sale_items
            SET catalog_unit_price_snapshot = NULL,
                price_override_reason = NULL
            WHERE source_type = 'free_concept';

            ALTER TABLE sales.sale_items
            ADD CONSTRAINT ck_sale_items_catalog_price CHECK ({_CATALOG_PRICE_CHECK});

            ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
        EXCEPTION
            WHEN OTHERS THEN
                ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
                ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
                RAISE;
        END
        $fn$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            override_rows integer;
        BEGIN
            ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY;
            SELECT count(*)::integer INTO override_rows
            FROM sales.sale_items
            WHERE source_type = 'catalog'
              AND (
                price_override_reason IS NOT NULL
                OR catalog_unit_price_snapshot IS DISTINCT FROM unit_price
              );
            IF override_rows > 0 THEN
                ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
                ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
                RAISE EXCEPTION 'cannot downgrade 0009 while a catalog price override exists';
            END IF;
            ALTER TABLE sales.sale_items DROP CONSTRAINT IF EXISTS ck_sale_items_catalog_price;
            ALTER TABLE sales.sale_items DROP COLUMN IF EXISTS price_override_reason;
            ALTER TABLE sales.sale_items DROP COLUMN IF EXISTS catalog_unit_price_snapshot;
            ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
        EXCEPTION
            WHEN OTHERS THEN
                ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
                ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
                RAISE;
        END
        $fn$;
        """
    )
