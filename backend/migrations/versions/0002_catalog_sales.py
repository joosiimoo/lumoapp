"""Create catalog and sales schemas for the conversational sale slice.

Revision ID: 0002_catalog_sales
Revises: 0001_foundation
Create Date: 2026-09-20
"""

from __future__ import annotations

from alembic import op

revision = "0002_catalog_sales"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS catalog")
    op.execute("CREATE SCHEMA IF NOT EXISTS sales")
    op.execute(
        """
        CREATE TABLE catalog.products (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            name VARCHAR(200) NOT NULL,
            normalized_name VARCHAR(200) NOT NULL,
            sale_unit VARCHAR(32) NOT NULL,
            pricing_type VARCHAR(32) NOT NULL,
            current_price NUMERIC(12, 2) NOT NULL,
            status VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_products_sale_unit CHECK (sale_unit IN ('unit', 'package', 'kilogram')),
            CONSTRAINT ck_products_pricing_type CHECK (pricing_type IN ('per_unit', 'per_package', 'per_kilogram')),
            CONSTRAINT ck_products_status CHECK (status IN ('active', 'inactive')),
            CONSTRAINT ck_products_pairing CHECK (
                (sale_unit = 'unit' AND pricing_type = 'per_unit')
                OR (sale_unit = 'package' AND pricing_type = 'per_package')
                OR (sale_unit = 'kilogram' AND pricing_type = 'per_kilogram')
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_products_business_id ON catalog.products (business_id)")
    op.execute(
        "CREATE INDEX ix_products_business_normalized_name ON catalog.products (business_id, normalized_name)"
    )
    op.execute(
        """
        CREATE TABLE catalog.product_aliases (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            product_id UUID NOT NULL REFERENCES catalog.products (id),
            alias VARCHAR(200) NOT NULL,
            normalized_alias VARCHAR(200) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_product_aliases_business_id ON catalog.product_aliases (business_id)")
    op.execute(
        """
        CREATE TABLE sales.sale_sessions (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            conversation_id VARCHAR(128) NULL,
            status VARCHAR(32) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_sale_sessions_status CHECK (status IN ('open'))
        )
        """
    )
    op.execute("CREATE INDEX ix_sale_sessions_business_id ON sales.sale_sessions (business_id)")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sale_sessions_open_context
        ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
        WHERE status = 'open'
        """
    )
    op.execute(
        """
        CREATE TABLE sales.sale_items (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            sale_session_id UUID NOT NULL REFERENCES sales.sale_sessions (id),
            product_id UUID NOT NULL REFERENCES catalog.products (id),
            product_name_snapshot VARCHAR(200) NOT NULL,
            quantity_input NUMERIC(14, 6) NOT NULL,
            unit_input VARCHAR(32) NOT NULL,
            quantity_normalized NUMERIC(14, 6) NOT NULL,
            unit_normalized VARCHAR(32) NOT NULL,
            unit_price NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            line_total NUMERIC(12, 2) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_sale_items_unit_input CHECK (unit_input IN ('gram', 'kilogram', 'unit', 'package')),
            CONSTRAINT ck_sale_items_unit_normalized CHECK (unit_normalized IN ('unit', 'package', 'kilogram'))
        )
        """
    )
    op.execute("CREATE INDEX ix_sale_items_business_id ON sales.sale_items (business_id)")
    op.execute("CREATE INDEX ix_sale_items_session_id ON sales.sale_items (sale_session_id)")

    tenant_tables = [
        ("catalog.products", "business_id"),
        ("catalog.product_aliases", "business_id"),
        ("sales.sale_sessions", "business_id"),
        ("sales.sale_items", "business_id"),
    ]
    for table, column in tenant_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING ({column}::text = current_setting('app.current_business_id', true))
            """
        )

    op.execute("GRANT USAGE ON SCHEMA catalog, sales TO lumo_app")
    for schema in ("catalog", "sales"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO lumo_app")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO lumo_app")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lumo_app"
        )
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT USAGE, SELECT ON SEQUENCES TO lumo_app")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS sales CASCADE")
    op.execute("DROP SCHEMA IF EXISTS catalog CASCADE")
