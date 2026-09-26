from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.bootstrap.settings import Settings, get_settings
from app.domain.shared.ids import new_uuid7
from tests.conftest import DEFAULT_ADMIN_URL, DEFAULT_APP_URL, TEST_SECRET, postgres_available, settings_kwargs

BACKEND = Path(__file__).resolve().parents[1]


def _config() -> Config:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("DATABASE_URL", DEFAULT_APP_URL)
    os.environ.setdefault("DATABASE_ADMIN_URL", DEFAULT_ADMIN_URL)
    os.environ.setdefault("DEV_TOKEN_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def _admin_engine():
    return create_engine(Settings.model_validate(settings_kwargs()).sqlalchemy_admin_url)


@pytest.fixture
def migrated():
    settings = Settings.model_validate(settings_kwargs())
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = _admin_engine()
    command.upgrade(_config(), "head")
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def test_0010_creates_work_items_without_backfill_or_extra_schemas(migrated) -> None:
    from tests.sale_cleanup import discard_work_items

    discard_work_items(migrated)
    command.downgrade(_config(), "0009_catalog_price_override")
    command.upgrade(_config(), "0010_work_items")
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0010_work_items"
        assert connection.execute(text("SELECT to_regclass('operations.work_items')")).scalar_one() is not None
        assert connection.execute(text("SELECT to_regclass('workflow.outcome_runs')")).scalar_one() is None
        assert connection.execute(text("SELECT to_regclass('public.next_best_actions')")).scalar_one() is None
        assert connection.execute(text("SELECT to_regclass('operations.next_best_actions')")).scalar_one() is None
        assert connection.execute(text("SELECT to_regclass('operations.outcome_runs')")).scalar_one() is None
        schemas = set(
            connection.execute(
                text("SELECT nspname FROM pg_namespace WHERE nspname IN ('workflow', 'memory')")
            ).scalars()
        )
        assert schemas == set()
        forced = connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class WHERE oid = 'operations.work_items'::regclass
                """
            )
        ).mappings().one()
        assert forced["relrowsecurity"] is True
        assert forced["relforcerowsecurity"] is True
        policy = connection.execute(
            text(
                """
                SELECT polname, pg_get_expr(polqual, polrelid)
                FROM pg_policy WHERE polrelid = 'operations.work_items'::regclass
                """
            )
        ).mappings().one()
        assert policy["polname"] == "tenant_isolation"
        assert "app.current_business_id" in policy["pg_get_expr"]
        indexdef = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_work_items_one_open'")
        ).scalar_one()
        assert "UNIQUE" in indexdef
        assert "((status)::text = 'open'::text)" in indexdef or "status = 'open'" in indexdef
        fk = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'fk_work_items_operational_day'
                """
            )
        ).scalar_one()
        assert "FOREIGN KEY (operational_day_id, business_id)" in fk
        assert "operations.operational_days" in fk
        checks = connection.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'operations.work_items'::regclass AND contype = 'c'
                """
            )
        ).scalars().all()
        assert "ck_work_items_resolution" in checks
        assert "ck_work_items_resolution_actor_type" in checks
        roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('lumo_admin', 'lumo_app')")
            )
        }
        assert roles["lumo_admin"] is False
        assert roles["lumo_app"] is False
        connection.execute(text("ALTER TABLE operations.work_items DISABLE ROW LEVEL SECURITY"))
        count = connection.execute(text("SELECT count(*) FROM operations.work_items")).scalar_one()
        connection.execute(text("ALTER TABLE operations.work_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.work_items FORCE ROW LEVEL SECURITY"))
        assert count == 0


def test_downgrade_aborts_while_a_work_item_exists(migrated) -> None:
    from tests.sale_cleanup import discard_work_items

    discard_work_items(migrated)
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.work_items DISABLE ROW LEVEL SECURITY"))
    business_id = new_uuid7()
    day_id = new_uuid7()
    with migrated.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
                VALUES (:id, 'Work item fixture', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
                """
            ),
            {"id": business_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO operations.operational_days (
                    id, business_id, business_date, status, timezone, created_at, updated_at
                ) VALUES (
                    :id, :business_id, DATE '2026-09-24', 'open', 'America/Mexico_City', now(), now()
                )
                """
            ),
            {"id": day_id, "business_id": business_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO operations.work_items (
                    id, business_id, operational_day_id, type, status, priority,
                    responsible_party, reason_code, source, evidence, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :day_id, 'cash_count_required', 'open', 'critical',
                    'business', 'cash_count_missing', 'daily_close_rule',
                    CAST(:evidence AS jsonb),
                    now(), now()
                )
                """
            ),
            {
                "id": new_uuid7(),
                "business_id": business_id,
                "day_id": day_id,
                "evidence": '{"currency":"MXN","expected_cash":"22.50","sale_count":1,"cash_status":"not_counted"}',
            },
        )
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE operations.work_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.work_items FORCE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))
    with pytest.raises(Exception, match="cannot downgrade 0010 while a work item exists"):
        command.downgrade(_config(), "0009_catalog_price_override")
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0012_source_coverage_event_memory"
        )
    discard_work_items(migrated)
