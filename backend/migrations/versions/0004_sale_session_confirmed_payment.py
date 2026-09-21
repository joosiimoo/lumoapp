"""Allow SaleSession confirmed and create sales.payments.

Revision ID: 0004_confirmed_payment
Revises: 0003_ready_to_charge
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision = "0004_confirmed_payment"
down_revision = "0003_ready_to_charge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT ck_sale_sessions_status")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_status
        CHECK (status IN ('open', 'ready_to_charge', 'confirmed'))
        """
    )
    op.execute(
        """
        CREATE TABLE sales.payments (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            sale_session_id UUID NOT NULL REFERENCES sales.sale_sessions (id),
            actor_id UUID NOT NULL,
            method VARCHAR(32) NOT NULL,
            amount NUMERIC(12, 2) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            status VARCHAR(32) NOT NULL,
            source VARCHAR(32) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_payments_method CHECK (method IN ('cash', 'card', 'transfer')),
            CONSTRAINT ck_payments_status CHECK (status IN ('recorded')),
            CONSTRAINT ck_payments_source CHECK (source IN ('manual_capture')),
            CONSTRAINT uq_payments_sale_session_id UNIQUE (sale_session_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_payments_business_id ON sales.payments (business_id)")
    op.execute("ALTER TABLE sales.payments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sales.payments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON sales.payments
        USING (business_id::text = current_setting('app.current_business_id', true))
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON sales.payments TO lumo_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sales.payments")
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT ck_sale_sessions_status")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_status
        CHECK (status IN ('open', 'ready_to_charge'))
        """
    )
