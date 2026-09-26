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

HEAD = "0012_source_coverage_event_memory"


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
        discard_work_items(engine)
        command.upgrade(_config(), "head")
        engine.dispose()


def test_0012_is_head_and_inserts_nothing(migrated) -> None:
    discard_work_items(migrated)
    command.downgrade(_config(), "0011_daily_close_outcome")
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('operations.source_coverage_records')")).scalar_one() is None
        assert connection.execute(text("SELECT to_regclass('operations.business_events')")).scalar_one() is None
    command.upgrade(_config(), "head")
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
        assert connection.execute(text("SELECT count(*) FROM operations.source_coverage_records")).scalar_one() == 0
        assert connection.execute(text("SELECT count(*) FROM operations.business_events")).scalar_one() == 0
        assert connection.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'")).first() is None
        schemas = set(
            connection.execute(
                text("SELECT nspname FROM pg_namespace WHERE nspname IN ('memory', 'workflow')")
            ).scalars()
        )
        assert schemas == set()
        for name in (
            "memory.events",
            "memory.memories",
            "memory.knowledge",
            "operations.embeddings",
            "operations.event_memory",
            "operations.source_coverage",
            "operations.recommendations",
            "public.memories",
        ):
            assert connection.execute(text("SELECT to_regclass(:name)"), {"name": name}).scalar_one() is None


def test_0012_schema_constraints_rls_and_immutability(migrated) -> None:
    with migrated.connect() as connection:
        coverage_columns = connection.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'operations' AND table_name = 'source_coverage_records'
                ORDER BY ordinal_position
                """
            )
        ).scalars().all()
        assert coverage_columns == [
            "id",
            "business_id",
            "operational_day_id",
            "domain",
            "source_type",
            "status",
            "limitation_code",
            "created_at",
        ]
        event_columns = connection.execute(
            text(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'operations' AND table_name = 'business_events'
                ORDER BY ordinal_position
                """
            )
        ).scalars().all()
        assert event_columns == [
            "id",
            "business_id",
            "operational_day_id",
            "event_type",
            "occurred_at",
            "source_type",
            "source_entity_type",
            "source_entity_id",
            "facts",
            "created_at",
        ]
        assert "updated_at" not in coverage_columns
        assert "updated_at" not in event_columns
        assert "embedding" not in event_columns
        for table in ("source_coverage_records", "business_events"):
            forced = connection.execute(
                text(
                    f"""
                    SELECT relrowsecurity, relforcerowsecurity
                    FROM pg_class WHERE oid = 'operations.{table}'::regclass
                    """
                )
            ).mappings().one()
            assert forced["relrowsecurity"] is True
            assert forced["relforcerowsecurity"] is True
            policy = connection.execute(
                text(
                    f"""
                    SELECT polname, pg_get_expr(polqual, polrelid)
                    FROM pg_policy WHERE polrelid = 'operations.{table}'::regclass
                    """
                )
            ).mappings().one()
            assert policy["polname"] == "tenant_isolation"
            assert "app.current_business_id" in policy["pg_get_expr"]
            grants = set(
                connection.execute(
                    text(
                        """
                        SELECT privilege_type FROM information_schema.role_table_grants
                        WHERE table_schema = 'operations' AND table_name = :table
                          AND grantee = 'lumo_app'
                        """
                    ),
                    {"table": table},
                ).scalars()
            )
            assert grants == {"SELECT", "INSERT", "DELETE"}
        roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('lumo_admin', 'lumo_app')")
            )
        }
        assert roles["lumo_admin"] is False
        assert roles["lumo_app"] is False
        trigger = connection.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'operations.business_events'::regclass
                  AND tgname = 'business_events_immutable'
                  AND NOT tgisinternal
                """
            )
        ).scalar_one()
        assert trigger == "business_events_immutable"
        for name in (
            "uq_source_coverage_records_identity",
            "fk_source_coverage_records_operational_day",
            "ck_source_coverage_records_domain",
            "ck_source_coverage_records_source_type",
            "ck_source_coverage_records_status",
            "ck_source_coverage_records_limitation",
            "uq_business_events_source",
            "fk_business_events_operational_day",
            "ck_business_events_source_type",
            "ck_business_events_shape",
        ):
            assert connection.execute(
                text("SELECT 1 FROM pg_constraint WHERE conname = :name"),
                {"name": name},
            ).scalar_one() == 1
        indexes = set(
            connection.execute(
                text(
                    """
                    SELECT indexname FROM pg_indexes
                    WHERE schemaname = 'operations'
                      AND indexname IN (
                        'ix_source_coverage_records_business_id',
                        'ix_business_events_business_day'
                      )
                    """
                )
            ).scalars()
        )
        assert indexes == {
            "ix_source_coverage_records_business_id",
            "ix_business_events_business_day",
        }

    business_id = new_uuid7()
    day_id = new_uuid7()
    event_id = new_uuid7()
    entity_id = new_uuid7()
    try:
        with migrated.begin() as connection:
            _tenant(connection, business_id)
            _insert_day(connection, business_id, day_id)
        with pytest.raises(IntegrityError):
            with migrated.begin() as connection:
                _tenant(connection, business_id)
                connection.execute(
                    text(
                        """
                        INSERT INTO operations.business_events (
                            id, business_id, operational_day_id, event_type, occurred_at,
                            source_type, source_entity_type, source_entity_id, facts, created_at
                        ) VALUES (
                            :id, :business_id, :day_id, 'sale_confirmed', now(),
                            'manual_capture', 'sale_session', :entity_id,
                            CAST(:facts AS jsonb), now()
                        )
                        """
                    ),
                    {
                        "id": new_uuid7(),
                        "business_id": business_id,
                        "day_id": day_id,
                        "entity_id": entity_id,
                        "facts": (
                            '{"sale_session_id":"' + str(entity_id) + '",'
                            '"payment_id":"00000000-0000-7000-8000-000000000098",'
                            '"payment_method":"cash","amount":"1.00","currency":"MXN","summary":"no"}'
                        ),
                    },
                )
        with migrated.begin() as connection:
            _tenant(connection, business_id)
            connection.execute(
                text(
                    """
                    INSERT INTO operations.business_events (
                        id, business_id, operational_day_id, event_type, occurred_at,
                        source_type, source_entity_type, source_entity_id, facts, created_at
                    ) VALUES (
                        :id, :business_id, :day_id, 'sale_confirmed', now(),
                        'manual_capture', 'sale_session', :entity_id,
                        CAST(:facts AS jsonb), now()
                    )
                    """
                ),
                {
                    "id": event_id,
                    "business_id": business_id,
                    "day_id": day_id,
                    "entity_id": entity_id,
                    "facts": (
                        '{"sale_session_id":"' + str(entity_id) + '",'
                        '"payment_id":"00000000-0000-7000-8000-000000000098",'
                        '"payment_method":"cash","amount":"1.00","currency":"MXN"}'
                    ),
                },
            )
        with pytest.raises(Exception, match="business events are immutable"):
            with migrated.begin() as connection:
                _tenant(connection, business_id)
                connection.execute(
                    text("UPDATE operations.business_events SET source_type = 'manual_capture' WHERE id = :id"),
                    {"id": event_id},
                )
    finally:
        with migrated.begin() as connection:
            _disable(connection)
            connection.execute(text("DELETE FROM operations.business_events WHERE business_id = :id"), {"id": business_id})
            connection.execute(
                text("DELETE FROM operations.source_coverage_records WHERE business_id = :id"),
                {"id": business_id},
            )
            connection.execute(text("DELETE FROM operations.operational_days WHERE business_id = :id"), {"id": business_id})
            connection.execute(text("DELETE FROM identity.businesses WHERE id = :id"), {"id": business_id})
        with migrated.begin() as connection:
            _enable(connection)


def test_downgrade_aborts_while_coverage_or_an_event_exists(migrated) -> None:
    discard_work_items(migrated)
    business_id = new_uuid7()
    day_id = new_uuid7()
    with migrated.begin() as connection:
        _tenant(connection, business_id)
        _insert_day(connection, business_id, day_id)
        connection.execute(
            text(
                """
                INSERT INTO operations.source_coverage_records (
                    id, business_id, operational_day_id, domain, source_type, status,
                    limitation_code, created_at
                ) VALUES (
                    :id, :business_id, :day_id, 'sales', 'manual_capture', 'observed',
                    'only_lumo_registered_operations', now()
                )
                """
            ),
            {"id": new_uuid7(), "business_id": business_id, "day_id": day_id},
        )
    with pytest.raises(Exception, match="cannot downgrade 0012 while source coverage or a business event exists"):
        command.downgrade(_config(), "0011_daily_close_outcome")
    with migrated.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
    with migrated.begin() as connection:
        _tenant(connection, business_id)
        connection.execute(text("DELETE FROM operations.source_coverage_records WHERE business_id = :id"), {"id": business_id})
        connection.execute(
            text(
                """
                INSERT INTO operations.business_events (
                    id, business_id, operational_day_id, event_type, occurred_at,
                    source_type, source_entity_type, source_entity_id, facts, created_at
                ) VALUES (
                    :id, :business_id, :day_id, 'cash_count_recorded', now(),
                    'manual_capture', 'cash_count', :entity_id,
                    CAST(:facts AS jsonb), now()
                )
                """
            ),
            {
                "id": new_uuid7(),
                "business_id": business_id,
                "day_id": day_id,
                "entity_id": "00000000-0000-7000-8000-0000000000aa",
                "facts": (
                    '{"cash_count_id":"00000000-0000-7000-8000-0000000000aa",'
                    '"expected_cash":"1.00","counted_cash":"1.00","cash_difference":"0.00",'
                    '"cash_status":"balanced","currency":"MXN"}'
                ),
            },
        )
    with pytest.raises(Exception, match="cannot downgrade 0012 while source coverage or a business event exists"):
        command.downgrade(_config(), "0011_daily_close_outcome")
    with migrated.begin() as connection:
        _disable(connection)
        connection.execute(text("DELETE FROM operations.business_events WHERE business_id = :id"), {"id": business_id})
        connection.execute(text("DELETE FROM operations.operational_days WHERE business_id = :id"), {"id": business_id})
        connection.execute(text("DELETE FROM identity.businesses WHERE id = :id"), {"id": business_id})
    with migrated.begin() as connection:
        _enable(connection)


def _tenant(connection, business_id) -> None:
    connection.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )


def _disable(connection) -> None:
    for table in (
        "identity.businesses",
        "operations.operational_days",
        "operations.source_coverage_records",
        "operations.business_events",
    ):
        connection.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))


def _enable(connection) -> None:
    for table in (
        "identity.businesses",
        "operations.operational_days",
        "operations.source_coverage_records",
        "operations.business_events",
    ):
        connection.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        connection.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))


def _insert_day(connection, business_id, day_id) -> None:
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, 'Coverage migration', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
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
                :id, :business_id, DATE '2026-09-20', 'open', 'America/Mexico_City', now(), now()
            )
            """
        ),
        {"id": day_id, "business_id": business_id},
    )
