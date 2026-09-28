from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from app.bootstrap.settings import Settings
from tests.conftest import postgres_available, settings_kwargs
from tests.sale_cleanup import discard_work_items
from tests.test_work_item_migration import _config

pytestmark = pytest.mark.schema_migration


@pytest.fixture
def migrated():
    settings = Settings.model_validate(settings_kwargs())
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = create_engine(settings.sqlalchemy_admin_url)
    command.upgrade(_config(), "head")
    discard_work_items(engine)
    command.downgrade(_config(), "0013_work_absorption_outcome_cost")
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def test_0013_creates_tables_without_backfill(migrated) -> None:
    discard_work_items(migrated)
    with migrated.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "0013_work_absorption_outcome_cost"
        assert connection.execute(text("SELECT to_regclass('operations.work_absorption_records')")).scalar() is not None
        assert connection.execute(text("SELECT to_regclass('operations.outcome_costs')")).scalar() is not None
        assert connection.execute(text("SELECT count(*) FROM operations.work_absorption_records")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM operations.outcome_costs")).scalar_one() == 0


def test_0013_downgrade_aborts_when_rows_exist(migrated) -> None:
    from app.domain.shared.ids import new_uuid7

    discard_work_items(migrated)
    business_id = new_uuid7()
    day_id = new_uuid7()
    outcome_id = new_uuid7()
    absorption_id = new_uuid7()
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                """
                INSERT INTO identity.businesses (id, name, currency, timezone, locale, status, created_at, updated_at)
                VALUES (:id, 'migration-test', 'MXN', 'America/Mexico_City', 'es-MX', 'active', now(), now())
                """
            ),
            {"id": business_id},
        )
        connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                """
                INSERT INTO operations.operational_days (
                    id, business_id, business_date, status, timezone, created_at, updated_at
                ) VALUES (:id, :business_id, '2026-09-01', 'open', 'America/Mexico_City', now(), now())
                """
            ),
            {"id": day_id, "business_id": business_id},
        )
        connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                """
                INSERT INTO operations.outcome_runs (
                    id, business_id, operational_day_id, outcome_type, outcome_version,
                    status, owner_type, reason_code, evidence, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :day_id, 'daily_close_ready', 1,
                    'in_progress', 'business', 'awaiting_cash_count',
                    CAST(:evidence AS jsonb),
                    now(), now()
                )
                """
            ),
            {
                "id": outcome_id,
                "business_id": business_id,
                "day_id": day_id,
                "evidence": (
                    '{"currency":"MXN","sale_count":1,"gross_sales_total":"1.00",'
                    '"expected_cash":"1.00","cash_status":"not_counted"}'
                ),
            },
        )
        connection.execute(text("ALTER TABLE operations.work_absorption_records DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                """
                INSERT INTO operations.work_absorption_records (
                    id, business_id, outcome_run_id, work_item_id, task_type,
                    previous_execution_mode, current_execution_mode,
                    human_steps_before, human_steps_after, estimated_minutes_saved,
                    business_intervention_seconds, internal_intervention_seconds,
                    automation_level, evidence_ids, baseline_version, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :outcome_id, NULL, 'organize_registered_sales',
                    'manual_by_business', 'fully_automated', 1, 0, 2,
                    NULL, NULL, 'automated', '[]'::jsonb,
                    'daily_close_ready@1/work_absorption_baseline@1', now(), now()
                )
                """
            ),
            {"id": absorption_id, "business_id": business_id, "outcome_id": outcome_id},
        )
    with pytest.raises(Exception, match="cannot downgrade 0013 while instrumentation rows exist"):
        command.downgrade(_config(), "0012_source_coverage_event_memory")
    discard_work_items(migrated)
    with migrated.begin() as connection:
        connection.execute(text("DELETE FROM identity.businesses WHERE id = :id"), {"id": business_id})
