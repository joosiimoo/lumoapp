"""Nullable product and free-concept sale lines.

Revision ID: 0008_noncatalog_sale_item
Revises: 0007_daily_close_confirmation
Create Date: 2026-09-23
"""

from __future__ import annotations

from alembic import op

revision = "0008_noncatalog_sale_item"
down_revision = "0007_daily_close_confirmation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # lumo_admin is NOBYPASSRLS. Lift RLS only while this migration backfills and
    # validates constraints, then force it back on before return.
    op.execute(
        """
        DO $fn$
        BEGIN
            ALTER TABLE catalog.products DISABLE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY;

            ALTER TABLE sales.sale_items ADD COLUMN source_type VARCHAR(32);
            UPDATE sales.sale_items SET source_type = 'catalog';
            ALTER TABLE sales.sale_items ALTER COLUMN source_type SET NOT NULL;
            ALTER TABLE sales.sale_items ALTER COLUMN product_id DROP NOT NULL;

            ALTER TABLE sales.sale_items
            ADD CONSTRAINT ck_sale_items_source CHECK (
                (source_type = 'catalog' AND product_id IS NOT NULL)
                OR (
                    source_type = 'free_concept'
                    AND product_id IS NULL
                    AND length(btrim(product_name_snapshot)) > 0
                )
            );
            ALTER TABLE sales.sale_items
            ADD CONSTRAINT ck_sale_items_money_positive CHECK (unit_price > 0 AND line_total > 0);

            ALTER TABLE catalog.products
            ADD CONSTRAINT uq_products_id_business UNIQUE (id, business_id);

            ALTER TABLE sales.sale_items
            ADD CONSTRAINT fk_sale_items_product_business
            FOREIGN KEY (product_id, business_id)
            REFERENCES catalog.products (id, business_id);

            ALTER TABLE catalog.products ENABLE ROW LEVEL SECURITY;
            ALTER TABLE catalog.products FORCE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
        END;
        $fn$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $fn$
        DECLARE
            free_rows integer;
        BEGIN
            ALTER TABLE catalog.products DISABLE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY;
            SELECT count(*)::integer INTO free_rows
            FROM sales.sale_items
            WHERE source_type = 'free_concept' OR product_id IS NULL;
            ALTER TABLE catalog.products ENABLE ROW LEVEL SECURITY;
            ALTER TABLE catalog.products FORCE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY;
            ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY;
            IF free_rows > 0 THEN
                RAISE EXCEPTION 'cannot downgrade 0008 while a free-concept sale item exists';
            END IF;
        END;
        $fn$
        """
    )
    op.execute("ALTER TABLE catalog.products DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.sale_items DROP CONSTRAINT IF EXISTS fk_sale_items_product_business")
    op.execute("ALTER TABLE sales.sale_items DROP CONSTRAINT IF EXISTS ck_sale_items_money_positive")
    op.execute("ALTER TABLE sales.sale_items DROP CONSTRAINT IF EXISTS ck_sale_items_source")
    op.execute("ALTER TABLE catalog.products DROP CONSTRAINT IF EXISTS uq_products_id_business")
    op.execute("ALTER TABLE sales.sale_items DROP COLUMN IF EXISTS source_type")
    op.execute("ALTER TABLE sales.sale_items ALTER COLUMN product_id SET NOT NULL")
    op.execute("ALTER TABLE catalog.products ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE catalog.products FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY")
