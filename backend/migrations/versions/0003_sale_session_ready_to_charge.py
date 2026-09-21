"""Allow SaleSession ready_to_charge and widen the active unique index.

Revision ID: 0003_ready_to_charge
Revises: 0002_catalog_sales
Create Date: 2026-09-21
"""

from __future__ import annotations

from alembic import op

revision = "0003_ready_to_charge"
down_revision = "0002_catalog_sales"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT ck_sale_sessions_status")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_status
        CHECK (status IN ('open', 'ready_to_charge'))
        """
    )
    op.execute("DROP INDEX sales.uq_sale_sessions_open_context")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sale_sessions_active_context
        ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
        WHERE status IN ('open', 'ready_to_charge')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX sales.uq_sale_sessions_active_context")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sale_sessions_open_context
        ON sales.sale_sessions (business_id, actor_id, COALESCE(conversation_id, ''))
        WHERE status = 'open'
        """
    )
    op.execute("ALTER TABLE sales.sale_sessions DROP CONSTRAINT ck_sale_sessions_status")
    op.execute(
        """
        ALTER TABLE sales.sale_sessions
        ADD CONSTRAINT ck_sale_sessions_status
        CHECK (status IN ('open'))
        """
    )
