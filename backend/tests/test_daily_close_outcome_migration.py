from __future__ import annotations

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.bootstrap.settings import Settings
from app.domain.shared.ids import new_uuid7
from tests.conftest import postgres_available, settings_kwargs
from tests.sale_cleanup import discard_work_items
from tests.test_work_item_migration import _config


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


def test_0011_creates_outcome_runs_without_backfill(migrated) -> None:
    discard_work_items(migrated)
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0011_daily_close_outcome"
        )
        assert connection.execute(text("SELECT to_regclass('operations.outcome_runs')")).scalar_one() is not None
        column = connection.execute(
            text(
                """
                SELECT is_nullable FROM information_schema.columns
                WHERE table_schema = 'operations' AND table_name = 'work_items'
                  AND column_name = 'outcome_run_id'
                """
            )
        ).scalar_one()
        assert column == "YES"
        forced = connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class WHERE oid = 'operations.outcome_runs'::regclass
                """
            )
        ).mappings().one()
        assert forced["relrowsecurity"] is True
        assert forced["relforcerowsecurity"] is True
        policy = connection.execute(
            text(
                """
                SELECT polname, pg_get_expr(polqual, polrelid)
                FROM pg_policy WHERE polrelid = 'operations.outcome_runs'::regclass
                """
            )
        ).mappings().one()
        assert policy["polname"] == "tenant_isolation"
        assert "app.current_business_id" in policy["pg_get_expr"]
        grants = connection.execute(
            text(
                """
                SELECT privilege_type FROM information_schema.role_table_grants
                WHERE table_schema = 'operations' AND table_name = 'outcome_runs'
                  AND grantee = 'lumo_app'
                """
            )
        ).scalars().all()
        assert set(grants) >= {"SELECT", "INSERT", "UPDATE", "DELETE"}
        roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('lumo_admin', 'lumo_app')")
            )
        }
        assert roles["lumo_admin"] is False
        assert roles["lumo_app"] is False
        absent = [
            "workflow.outcome_runs",
            "memory.outcome_runs",
            "operations.outcome_definitions",
            "operations.completion_evidence",
            "operations.next_best_actions",
            "public.next_best_actions",
            "operations.source_coverage",
            "operations.event_memory",
            "operations.outcome_costs",
        ]
        for name in absent:
            assert connection.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar_one() is None
        schemas = set(
            connection.execute(
                text("SELECT nspname FROM pg_namespace WHERE nspname IN ('workflow', 'memory')")
            ).scalars()
        )
        assert schemas == set()
        identity = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'uq_outcome_runs_identity'
                """
            )
        ).scalar_one()
        assert "business_id" in identity and "operational_day_id" in identity
        snapshot_key = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'uq_closing_snapshots_id_business_day'
                """
            )
        ).scalar_one()
        assert "operational_day_id" in snapshot_key
        work_fk = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conname = 'fk_work_items_outcome_run'
                """
            )
        ).scalar_one()
        assert "FOREIGN KEY (outcome_run_id, business_id, operational_day_id)" in work_fk
        connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
        count = connection.execute(text("SELECT count(*) FROM operations.outcome_runs")).scalar_one()
        connection.execute(text("ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY"))
        assert count == 0


def test_status_check_rejects_not_ready(migrated) -> None:
    business_id = new_uuid7()
    day_id = new_uuid7()
    try:
        with migrated.begin() as connection:
            connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
            connection.execute(
                text(
                    """
                    INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
                    VALUES (:id, 'Outcome check', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
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
        with pytest.raises(IntegrityError):
            with migrated.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO operations.outcome_runs (
                            id, business_id, operational_day_id, outcome_type, outcome_version,
                            status, owner_type, reason_code, evidence, created_at, updated_at
                        ) VALUES (
                            :id, :business_id, :day_id, 'daily_close_ready', 1,
                            'not_ready', 'business', 'awaiting_cash_count',
                            CAST(:evidence AS jsonb),
                            now(), now()
                        )
                        """
                    ),
                    {
                        "id": new_uuid7(),
                        "business_id": business_id,
                        "day_id": day_id,
                        "evidence": (
                            '{"currency":"MXN","sale_count":1,"gross_sales_total":"1.00",'
                            '"expected_cash":"1.00","cash_status":"not_counted"}'
                        ),
                    },
                )
    finally:
        with migrated.begin() as connection:
            connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
            connection.execute(text("DELETE FROM operations.outcome_runs WHERE business_id = :id"), {"id": business_id})
            connection.execute(
                text("DELETE FROM operations.operational_days WHERE business_id = :id"),
                {"id": business_id},
            )
            connection.execute(text("DELETE FROM identity.businesses WHERE id = :id"), {"id": business_id})
        with migrated.begin() as connection:
            connection.execute(text("ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
            connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))


def test_downgrade_aborts_while_an_outcome_exists(migrated) -> None:
    discard_work_items(migrated)
    business_id = new_uuid7()
    day_id = new_uuid7()
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.outcome_runs DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                """
                INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
                VALUES (:id, 'Outcome downgrade', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
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
                "id": new_uuid7(),
                "business_id": business_id,
                "day_id": day_id,
                "evidence": (
                    '{"currency":"MXN","sale_count":1,"gross_sales_total":"1.00",'
                    '"expected_cash":"1.00","cash_status":"not_counted"}'
                ),
            },
        )
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.outcome_runs ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.outcome_runs FORCE ROW LEVEL SECURITY"))
    with pytest.raises(Exception, match="cannot downgrade 0011 while an outcome run exists"):
        command.downgrade(_config(), "0010_work_items")
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0011_daily_close_outcome"
        )
    discard_work_items(migrated)
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("DELETE FROM operations.operational_days WHERE id = :id"), {"id": day_id})
        connection.execute(text("DELETE FROM identity.businesses WHERE id = :id"), {"id": business_id})
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))
