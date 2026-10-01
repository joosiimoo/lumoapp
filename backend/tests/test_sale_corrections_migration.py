"""Clean base→head proof for 0016_sale_corrections on a disposable database."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.bootstrap.settings import Settings, get_settings
from app.domain.shared.ids import new_uuid7
from tests.conftest import TEST_SECRET, postgres_available, settings_kwargs
from tests.migration_db import use_clean_proof_database

BACKEND = Path(__file__).resolve().parents[1]
HEAD = "0018_transaction_references"

pytestmark = pytest.mark.schema_migration


def _config() -> Config:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("DEV_TOKEN_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def _admin_engine():
    return create_engine(Settings.model_validate(settings_kwargs()).sqlalchemy_admin_url)


def _app_engine():
    return create_engine(Settings.model_validate(settings_kwargs()).sqlalchemy_url)


def _revision(engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _assert_0016_constraints(engine) -> None:
    with engine.connect() as connection:
        default = connection.execute(
            text(
                """
                SELECT column_default FROM information_schema.columns
                WHERE table_schema = 'sales'
                  AND table_name = 'sale_sessions'
                  AND column_name = 'sale_revision'
                """
            )
        ).scalar()
        assert default is not None
        assert "1" in default
        names = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT conname FROM pg_constraint
                    WHERE conname IN (
                        'ck_sale_sessions_sale_revision',
                        'ck_sale_sessions_void_metadata',
                        'ck_sale_sessions_status',
                        'ck_sale_sessions_day_membership',
                        'ck_business_events_shape'
                    )
                    """
                )
            ).fetchall()
        }
        assert names == {
            "ck_sale_sessions_sale_revision",
            "ck_sale_sessions_void_metadata",
            "ck_sale_sessions_status",
            "ck_sale_sessions_day_membership",
            "ck_business_events_shape",
        }
        status = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_sale_sessions_status'
                """
            )
        ).scalar_one()
        assert "voided" in status
        membership = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_sale_sessions_day_membership'
                """
            )
        ).scalar_one()
        assert "voided" in membership
        shape = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_business_events_shape'
                """
            )
        ).scalar_one()
        assert "sale_voided" in shape
        rls = connection.execute(
            text(
                """
                SELECT c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'sales' AND c.relname = 'sale_sessions'
                """
            )
        ).one()
        assert rls[0] is True and rls[1] is True


def test_0016_applies_cleanly_from_base_on_disposable_db() -> None:
    if not postgres_available(Settings.model_validate(settings_kwargs())):
        pytest.skip("PostgreSQL is not available")

    with use_clean_proof_database():
        cfg = _config()
        command.upgrade(cfg, "head")
        admin = _admin_engine()
        app = _app_engine()
        try:
            assert _revision(admin) == HEAD
            _assert_0016_constraints(admin)

            # App role cannot see another tenant's voided session under forced RLS.
            with admin.begin() as connection:
                business_a = new_uuid7()
                business_b = new_uuid7()
                actor_a = new_uuid7()
                day_a = new_uuid7()
                session_a = new_uuid7()
                for business_id, name in ((business_a, "A"), (business_b, "B")):
                    connection.execute(
                        text("SELECT set_config('app.current_business_id', :id, true)"),
                        {"id": str(business_id)},
                    )
                    connection.execute(
                        text(
                            """
                            INSERT INTO identity.businesses
                                (id, name, currency, timezone, locale, status)
                            VALUES
                                (:id, :name, 'MXN', 'America/Mexico_City', 'es-MX', 'active')
                            """
                        ),
                        {"id": business_id, "name": name},
                    )
                connection.execute(
                    text("SELECT set_config('app.current_business_id', :id, true)"),
                    {"id": str(business_a)},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO identity.users (id, business_id, name)
                        VALUES (:id, :business_id, 'Owner A')
                        """
                    ),
                    {"id": actor_a, "business_id": business_a},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO operations.operational_days (
                            id, business_id, business_date, status, timezone, created_at, updated_at
                        ) VALUES (
                            :id, :business_id, DATE '2026-09-29', 'open',
                            'America/Mexico_City', NOW(), NOW()
                        )
                        """
                    ),
                    {"id": day_a, "business_id": business_a},
                )
                connection.execute(
                    text(
                        """
                        INSERT INTO sales.sale_sessions (
                            id, business_id, actor_id, conversation_id, status, currency,
                            operational_day_id, confirmed_at, sale_revision,
                            voided_at, voided_by_actor_id, void_reason,
                            transaction_sequence, void_transaction_sequence
                        ) VALUES (
                            :id, :business_id, :actor_id, 'conv', 'voided', 'MXN',
                            :day_id, NOW(), 1, NOW(), :actor_id, 'rls check', 1, 2
                        )
                        """
                    ),
                    {
                        "id": session_a,
                        "business_id": business_a,
                        "actor_id": actor_a,
                        "day_id": day_a,
                    },
                )

            with app.connect() as connection:
                connection.execute(
                    text("SELECT set_config('app.current_business_id', :id, true)"),
                    {"id": str(business_b)},
                )
                visible = connection.execute(
                    text("SELECT id FROM sales.sale_sessions WHERE id = :id"),
                    {"id": session_a},
                ).first()
                assert visible is None
                connection.execute(
                    text("SELECT set_config('app.current_business_id', :id, true)"),
                    {"id": str(business_a)},
                )
                own = connection.execute(
                    text(
                        """
                        SELECT status, sale_revision, void_reason
                        FROM sales.sale_sessions WHERE id = :id
                        """
                    ),
                    {"id": session_a},
                ).one()
                assert own[0] == "voided"
                assert own[1] == 1
                assert own[2] == "rls check"
        finally:
            app.dispose()
            admin.dispose()
