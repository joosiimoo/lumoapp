from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from app.bootstrap.settings import Settings
from app.domain.shared.ids import new_uuid7
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
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def test_0014_creates_tables_without_backfill(migrated) -> None:
    discard_work_items(migrated)
    with migrated.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        assert version == "0014_pilot_stage_gate_instrumentation"
        assert connection.execute(text("SELECT to_regclass('operations.pilot_program_enrollments')")).scalar()
        assert connection.execute(text("SELECT to_regclass('operations.stage_gate_assessments')")).scalar()
        assert connection.execute(text("SELECT count(*) FROM operations.stage_gate_assessments")).scalar_one() == 0


def test_0014_installs_immutability_triggers(migrated) -> None:
    with migrated.connect() as connection:
        perception_trigger = connection.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'operations.pilot_perception_responses'::regclass
                  AND tgname = 'pilot_perception_responses_append_only'
                """
            )
        ).scalar_one_or_none()
        assessment_trigger = connection.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'operations.stage_gate_assessments'::regclass
                  AND tgname = 'stage_gate_assessments_immutable'
                """
            )
        ).scalar_one_or_none()
        assert perception_trigger == "pilot_perception_responses_append_only"
        assert assessment_trigger == "stage_gate_assessments_immutable"
        exclusion = connection.execute(
            text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'operations.pilot_program_enrollments'::regclass
                  AND conname = 'excl_pilot_program_enrollments_no_overlap'
                """
            )
        ).scalar_one_or_none()
        assert exclusion == "excl_pilot_program_enrollments_no_overlap"


def test_0014_downgrade_blocked_when_rows_exist(migrated) -> None:
    business_id = new_uuid7()
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text("ALTER TABLE operations.pilot_program_enrollments DISABLE ROW LEVEL SECURITY")
        )
    with migrated.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
                VALUES (:id, 'Pilot Downgrade', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
                """
            ),
            {"id": business_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO operations.pilot_program_enrollments (
                    id, business_id, cohort_code, pilot_started_on, created_at
                ) VALUES (:id, :business_id, 'cohort', '2026-09-01', '2026-09-01T00:00:00Z')
                """
            ),
            {"id": new_uuid7(), "business_id": business_id},
        )
    with pytest.raises(DBAPIError, match="cannot downgrade 0014"):
        command.downgrade(_config(), "0013_work_absorption_outcome_cost")
    command.upgrade(_config(), "head")
