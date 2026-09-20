"""Create identity, audit, and platform foundation schemas.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-09-20
"""

from __future__ import annotations

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS identity")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("CREATE SCHEMA IF NOT EXISTS platform")
    op.execute(
        """
        CREATE TABLE identity.businesses (
            id UUID PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            currency VARCHAR(3) NOT NULL,
            timezone VARCHAR(64) NOT NULL,
            locale VARCHAR(16) NOT NULL DEFAULT 'es-MX',
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE identity.users (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            name VARCHAR(200) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_users_business_id ON identity.users (business_id)")
    op.execute(
        """
        CREATE TABLE identity.memberships (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            user_id UUID NOT NULL REFERENCES identity.users (id),
            role VARCHAR(64) NOT NULL DEFAULT 'owner',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_memberships_business_user UNIQUE (business_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_memberships_business_id ON identity.memberships (business_id)")
    op.execute(
        """
        CREATE TABLE audit.audit_events (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            actor_id UUID NULL,
            action VARCHAR(128) NOT NULL,
            route_or_tool VARCHAR(128) NULL,
            policy_decision JSONB NULL,
            before_payload JSONB NULL,
            after_payload JSONB NULL,
            result VARCHAR(32) NOT NULL,
            correlation_id VARCHAR(64) NOT NULL,
            idempotency_key VARCHAR(128) NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_events_business_id ON audit.audit_events (business_id)")
    op.execute(
        """
        CREATE TABLE platform.idempotency_records (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            operation_type VARCHAR(64) NOT NULL,
            key VARCHAR(128) NOT NULL,
            request_hash VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL,
            response_status INTEGER NULL,
            response_body JSONB NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_idempotency_business_operation_key UNIQUE (business_id, operation_type, key),
            CONSTRAINT ck_idempotency_status CHECK (status IN ('processing', 'completed', 'failed'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE platform.outbox_events (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            event_type VARCHAR(128) NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX ix_outbox_events_business_id ON platform.outbox_events (business_id)")
    op.execute(
        """
        CREATE TABLE platform.foundation_notes (
            id UUID PRIMARY KEY,
            business_id UUID NOT NULL,
            actor_id UUID NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_foundation_notes_business_id ON platform.foundation_notes (business_id)"
    )

    tenant_tables = [
        ("identity.users", "business_id"),
        ("identity.memberships", "business_id"),
        ("audit.audit_events", "business_id"),
        ("platform.idempotency_records", "business_id"),
        ("platform.outbox_events", "business_id"),
        ("platform.foundation_notes", "business_id"),
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
    op.execute("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON identity.businesses
        USING (id::text = current_setting('app.current_business_id', true))
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lumo_app') THEN
            RAISE EXCEPTION 'role lumo_app must exist before migrations';
          END IF;
        END $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA identity, audit, platform TO lumo_app")
    for schema in ("identity", "audit", "platform"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO lumo_app")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO lumo_app")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO lumo_app"
        )
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT USAGE, SELECT ON SEQUENCES TO lumo_app")


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS platform CASCADE")
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS identity CASCADE")
