from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.bootstrap.settings import Settings, get_settings
from app.domain.shared.ids import new_uuid7
from tests.conftest import DEFAULT_ADMIN_URL, DEFAULT_APP_URL, TEST_SECRET, postgres_available, settings_kwargs
from tests.sale_cleanup import discard_work_items, isolate_database_for_0007_downgrade

BACKEND = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.schema_migration
STAMP = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)


def _config() -> Config:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("DATABASE_URL", DEFAULT_APP_URL)
    os.environ.setdefault("DATABASE_ADMIN_URL", DEFAULT_ADMIN_URL)
    os.environ.setdefault("DEV_TOKEN_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def _engine():
    settings = Settings.model_validate(settings_kwargs())
    return create_engine(settings.sqlalchemy_admin_url)


def _app_engine():
    settings = Settings.model_validate(settings_kwargs())
    return create_engine(settings.sqlalchemy_url)


def _revision(engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


@pytest.fixture
def admin_engine():
    settings = Settings.model_validate(settings_kwargs())
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = _engine()
    command.upgrade(_config(), "head")
    try:
        yield engine
    finally:
        command.upgrade(_config(), "head")
        engine.dispose()


def _tenant(connection, business_id: UUID | str) -> None:
    connection.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )


def _insert_business(connection) -> UUID:
    business_id = new_uuid7()
    _tenant(connection, business_id)
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, 'Close fixture', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
            """
        ),
        {"id": business_id},
    )
    return business_id


def _insert_day(connection, business_id: UUID, *, status: str = "open") -> UUID:
    day_id = new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO operations.operational_days (
                id, business_id, business_date, status, timezone, created_at, updated_at
            ) VALUES (
                :id, :business_id, DATE '2026-09-22', :status, 'America/Mexico_City', :at, :at
            )
            """
        ),
        {"id": day_id, "business_id": business_id, "status": status, "at": STAMP},
    )
    return day_id


def _insert_count(connection, business_id: UUID, day_id: UUID) -> UUID:
    count_id = new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO operations.cash_counts (
                id, business_id, operational_day_id, actor_id, amount, currency, source,
                counted_at, created_at, updated_at
            ) VALUES (
                :id, :business_id, :day_id, :actor_id, 22.50, 'MXN', 'manual_capture',
                :at, :at, :at
            )
            """
        ),
        {"id": count_id, "business_id": business_id, "day_id": day_id, "actor_id": new_uuid7(), "at": STAMP},
    )
    return count_id


def _insert_snapshot(connection, business_id: UUID, day_id: UUID, count_id: UUID) -> UUID:
    snapshot_id = new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO operations.closing_snapshots (
                id, business_id, operational_day_id, cash_count_id, actor_id, business_date,
                currency, sale_count, gross_sales_total, cash_total, card_total, transfer_total,
                expected_cash, counted_cash, cash_difference, cash_status, closed_at, created_at, updated_at
            ) VALUES (
                :id, :business_id, :day_id, :count_id, :actor_id, DATE '2026-09-22',
                'MXN', 1, 22.50, 22.50, 0, 0,
                22.50, 22.50, 0, 'balanced', :at, :at, :at
            )
            """
        ),
        {
            "id": snapshot_id,
            "business_id": business_id,
            "day_id": day_id,
            "count_id": count_id,
            "actor_id": new_uuid7(),
            "at": STAMP,
        },
    )
    return snapshot_id


def _close_pair(connection, business_id: UUID) -> dict:
    day_id = _insert_day(connection, business_id, status="open")
    count_id = _insert_count(connection, business_id, day_id)
    snapshot_id = _insert_snapshot(connection, business_id, day_id, count_id)
    connection.execute(
        text("UPDATE operations.operational_days SET status = 'closed', updated_at = :at WHERE id = :id"),
        {"id": day_id, "at": STAMP},
    )
    return {"business_id": business_id, "day_id": day_id, "count_id": count_id, "snapshot_id": snapshot_id}


def test_upgrade_from_0006_keeps_open_days_and_adds_snapshots(admin_engine) -> None:
    isolate_database_for_0007_downgrade(admin_engine)
    command.downgrade(_config(), "0006_cash_count")
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        day_id = _insert_day(connection, business_id)
    command.upgrade(_config(), "head")
    assert _revision(admin_engine) == "0012_source_coverage_event_memory"
    with admin_engine.begin() as connection:
        _tenant(connection, business_id)
        status = connection.execute(
            text("SELECT status FROM operations.operational_days WHERE id = :id"),
            {"id": day_id},
        ).scalar_one()
        assert status == "open"
        assert connection.execute(text("SELECT to_regclass('operations.closing_snapshots')")).scalar_one()
        check = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_operational_days_status'
                """
            )
        ).scalar_one()
        assert "closed" in check
        assert "open" in check


def test_unconfirmed_downgrade_returns_to_0006(admin_engine) -> None:
    isolate_database_for_0007_downgrade(admin_engine)
    command.downgrade(_config(), "0006_cash_count")
    assert _revision(admin_engine) == "0006_cash_count"
    with admin_engine.begin() as connection:
        assert connection.execute(text("SELECT to_regclass('operations.closing_snapshots')")).scalar_one() is None
        check = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_operational_days_status'
                """
            )
        ).scalar_one()
        assert "closed" not in check
    command.upgrade(_config(), "head")


def test_downgrade_refuses_when_a_confirmed_close_exists(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        closed = _close_pair(connection, business_id)
    discard_work_items(admin_engine)
    with pytest.raises(Exception, match="cannot downgrade 0007 while a confirmed close exists"):
        command.downgrade(_config(), "0006_cash_count")
    assert _revision(admin_engine) == "0012_source_coverage_event_memory"
    with admin_engine.begin() as connection:
        _tenant(connection, business_id)
        status = connection.execute(
            text("SELECT status FROM operations.operational_days WHERE id = :id"),
            {"id": closed["day_id"]},
        ).scalar_one()
        snapshots = connection.execute(
            text("SELECT count(*) FROM operations.closing_snapshots WHERE id = :id"),
            {"id": closed["snapshot_id"]},
        ).scalar_one()
    assert status == "closed"
    assert snapshots == 1
    isolate_database_for_0007_downgrade(admin_engine)


def test_closed_day_without_snapshot_fails_at_commit(admin_engine) -> None:
    with pytest.raises(DBAPIError, match="closed day must have exactly one snapshot"):
        with admin_engine.begin() as connection:
            business_id = _insert_business(connection)
            day_id = _insert_day(connection, business_id)
            connection.execute(
                text("UPDATE operations.operational_days SET status = 'closed' WHERE id = :id"),
                {"id": day_id},
            )


def test_snapshot_on_open_day_fails_at_commit(admin_engine) -> None:
    with pytest.raises(DBAPIError, match="open day must have zero snapshots"):
        with admin_engine.begin() as connection:
            business_id = _insert_business(connection)
            day_id = _insert_day(connection, business_id)
            count_id = _insert_count(connection, business_id, day_id)
            _insert_snapshot(connection, business_id, day_id, count_id)


def test_valid_snapshot_and_closed_day_commit(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        closed = _close_pair(connection, business_id)
    with admin_engine.begin() as connection:
        _tenant(connection, business_id)
        count = connection.execute(
            text("SELECT count(*) FROM operations.closing_snapshots WHERE operational_day_id = :id"),
            {"id": closed["day_id"]},
        ).scalar_one()
        status = connection.execute(
            text("SELECT status FROM operations.operational_days WHERE id = :id"),
            {"id": closed["day_id"]},
        ).scalar_one()
    assert count == 1
    assert status == "closed"


def test_deleting_snapshot_of_closed_day_fails(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        closed = _close_pair(connection, business_id)
    with pytest.raises(DBAPIError, match="closed day must have exactly one snapshot"):
        with admin_engine.begin() as connection:
            _tenant(connection, business_id)
            connection.execute(
                text("DELETE FROM operations.closing_snapshots WHERE id = :id"),
                {"id": closed["snapshot_id"]},
            )


def test_snapshot_count_and_day_cleanup_commits(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        closed = _close_pair(connection, business_id)
    with admin_engine.begin() as connection:
        _tenant(connection, business_id)
        connection.execute(
            text("DELETE FROM operations.closing_snapshots WHERE id = :id"),
            {"id": closed["snapshot_id"]},
        )
        connection.execute(
            text("DELETE FROM operations.cash_counts WHERE id = :id"),
            {"id": closed["count_id"]},
        )
        connection.execute(
            text("DELETE FROM operations.operational_days WHERE id = :id"),
            {"id": closed["day_id"]},
        )
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        setting = connection.execute(text("SELECT current_setting('app.current_business_id', true)")).scalar_one()
    assert setting == str(business_id)
    with admin_engine.begin() as connection:
        _tenant(connection, business_id)
        assert connection.execute(
            text("SELECT count(*) FROM operations.operational_days WHERE id = :id"),
            {"id": closed["day_id"]},
        ).scalar_one() == 0


def test_snapshot_update_is_immutable(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        closed = _close_pair(connection, business_id)
    with pytest.raises(DBAPIError, match="closing snapshots are immutable"):
        with admin_engine.begin() as connection:
            _tenant(connection, business_id)
            connection.execute(
                text("UPDATE operations.closing_snapshots SET sale_count = 2 WHERE id = :id"),
                {"id": closed["snapshot_id"]},
            )


def test_open_day_has_zero_snapshots_and_second_snapshot_fails(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        day_id = _insert_day(connection, business_id)
    with admin_engine.begin() as connection:
        _tenant(connection, business_id)
        assert connection.execute(
            text("SELECT count(*) FROM operations.closing_snapshots WHERE operational_day_id = :id"),
            {"id": day_id},
        ).scalar_one() == 0
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        closed = _close_pair(connection, business_id)
    with pytest.raises(IntegrityError, match="uq_closing_snapshots_operational_day"):
        with admin_engine.begin() as connection:
            _tenant(connection, business_id)
            extra_count = new_uuid7()
            connection.execute(
                text(
                    """
                    INSERT INTO operations.cash_counts (
                        id, business_id, operational_day_id, actor_id, amount, currency, source,
                        counted_at, created_at, updated_at, superseded_by_id
                    ) VALUES (
                        :id, :business_id, :day_id, :actor_id, 20.00, 'MXN', 'manual_capture',
                        :at, :at, :at, :current_id
                    )
                    """
                ),
                {
                    "id": extra_count,
                    "business_id": business_id,
                    "day_id": closed["day_id"],
                    "actor_id": new_uuid7(),
                    "at": STAMP,
                    "current_id": closed["count_id"],
                },
            )
            _insert_snapshot(connection, business_id, closed["day_id"], extra_count)


def test_deferred_triggers_are_constraint_triggers(admin_engine) -> None:
    with admin_engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT tgname, tgdeferrable, tginitdeferred
                FROM pg_trigger
                WHERE tgname IN ('closing_snapshots_match_day', 'operational_days_match_snapshot')
                ORDER BY tgname
                """
            )
        ).all()
    assert [row.tgname for row in rows] == [
        "closing_snapshots_match_day",
        "operational_days_match_snapshot",
    ]
    assert all(row.tgdeferrable and row.tginitdeferred for row in rows)


def test_force_rls_and_no_bypass(admin_engine) -> None:
    with admin_engine.begin() as connection:
        roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('lumo_admin', 'lumo_app')")
            )
        }
        forced = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'operations' AND c.relname = 'closing_snapshots'
                """
            )
        ).one()
        definer = connection.execute(
            text(
                """
                SELECT prosecdef, proconfig
                FROM pg_proc
                WHERE proname = 'assert_closing_snapshot_cardinality'
                """
            )
        ).one()
        bypass = connection.execute(
            text("SELECT count(*) FROM pg_roles WHERE rolbypassrls AND rolname LIKE 'lumo%'")
        ).scalar_one()
        grants = {
            row.privilege_type
            for row in connection.execute(
                text(
                    """
                    SELECT privilege_type
                    FROM information_schema.role_table_grants
                    WHERE table_schema = 'operations'
                      AND table_name = 'closing_snapshots'
                      AND grantee = 'lumo_app'
                    """
                )
            )
        }
    assert roles == {"lumo_admin": False, "lumo_app": False}
    assert forced.relrowsecurity is True
    assert forced.relforcerowsecurity is True
    assert definer.prosecdef is True
    assert definer.proconfig == ["search_path=operations, pg_temp"]
    assert bypass == 0
    assert grants == {"SELECT", "INSERT", "DELETE"}


def test_unset_guc_before_commit_still_rejects_invalid_cardinality(admin_engine) -> None:
    with pytest.raises(DBAPIError, match="closed day must have exactly one snapshot"):
        with admin_engine.begin() as connection:
            business_id = _insert_business(connection)
            day_id = _insert_day(connection, business_id)
            connection.execute(
                text("UPDATE operations.operational_days SET status = 'closed' WHERE id = :id"),
                {"id": day_id},
            )
            connection.execute(text("SELECT set_config('app.current_business_id', '', true)"))
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_wrong_tenant_before_commit_still_validates_affected_business(admin_engine) -> None:
    with admin_engine.begin() as connection:
        affected = _insert_business(connection)
        other = _insert_business(connection)
        _tenant(connection, affected)
        day_id = _insert_day(connection, affected)
    with pytest.raises(DBAPIError, match="closed day must have exactly one snapshot"):
        with admin_engine.begin() as connection:
            _tenant(connection, affected)
            connection.execute(
                text("UPDATE operations.operational_days SET status = 'closed' WHERE id = :id"),
                {"id": day_id},
            )
            _tenant(connection, other)
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))


def test_existing_tenant_is_restored_after_successful_validation(admin_engine) -> None:
    with admin_engine.begin() as connection:
        caller = _insert_business(connection)
        affected = _insert_business(connection)
    with admin_engine.begin() as connection:
        _tenant(connection, affected)
        _close_pair(connection, affected)
        _tenant(connection, caller)
        connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        setting = connection.execute(text("SELECT current_setting('app.current_business_id', true)")).scalar_one()
    assert setting == str(caller)
    assert setting != str(affected)


def test_existing_tenant_is_restored_after_validation_error(admin_engine) -> None:
    with admin_engine.begin() as connection:
        caller = _insert_business(connection)
        affected = _insert_business(connection)
        day_id = _insert_day(connection, affected)
    with admin_engine.connect() as connection:
        connection.execute(
            text("SELECT set_config('app.current_business_id', :business_id, false)"),
            {"business_id": str(caller)},
        )
        connection.commit()
        failed = connection.begin()
        try:
            connection.execute(
                text("SELECT set_config('app.current_business_id', :business_id, true)"),
                {"business_id": str(affected)},
            )
            connection.execute(
                text("UPDATE operations.operational_days SET status = 'closed' WHERE id = :id"),
                {"id": day_id},
            )
            connection.execute(
                text("SELECT set_config('app.current_business_id', :business_id, true)"),
                {"business_id": str(caller)},
            )
            with pytest.raises(DBAPIError, match="closed day must have exactly one snapshot"):
                connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
        finally:
            failed.rollback()
        setting = connection.execute(text("SELECT current_setting('app.current_business_id', true)")).scalar_one()
        connection.execute(text("RESET app.current_business_id"))
        connection.commit()
    assert setting == str(caller)


def test_previously_unset_guc_is_effectively_unset_after_validator(admin_engine) -> None:
    with admin_engine.connect() as connection:
        before = connection.execute(text("SELECT current_setting('app.current_business_id', true)")).scalar_one()
        assert before is None
        connection.rollback()
        transaction = connection.begin()
        business_id = new_uuid7()
        day_id = new_uuid7()
        try:
            setting, visible, matched = _unset_guc_validation(connection, business_id, day_id)
        finally:
            transaction.rollback()
    assert setting == ""
    assert setting != str(business_id)
    assert visible == 0
    assert matched == 0


def _unset_guc_validation(connection, business_id, day_id):
    connection.execute(text("ALTER TABLE operations.operational_days DISABLE ROW LEVEL SECURITY"))
    connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, 'Unset GUC', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
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
                :id, :business_id, DATE '2026-09-22', 'open', 'America/Mexico_City', :at, :at
            )
            """
        ),
        {"id": day_id, "business_id": business_id, "at": STAMP},
    )
    still_unset = connection.execute(text("SELECT current_setting('app.current_business_id', true)")).scalar_one()
    assert still_unset is None
    connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
    connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
    connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))
    connection.execute(text("ALTER TABLE operations.operational_days ENABLE ROW LEVEL SECURITY"))
    connection.execute(text("ALTER TABLE operations.operational_days FORCE ROW LEVEL SECURITY"))
    setting = connection.execute(text("SELECT current_setting('app.current_business_id', true)")).scalar_one()
    visible = connection.execute(text("SELECT count(*) FROM operations.operational_days")).scalar_one()
    matched = connection.execute(
        text(
            """
            SELECT count(*)
            FROM operations.operational_days
            WHERE business_id::text = current_setting('app.current_business_id', true)
            """
        )
    ).scalar_one()
    return setting, visible, matched


def test_empty_guc_matches_no_tenant_rows(admin_engine) -> None:
    with admin_engine.begin() as connection:
        business_id = _insert_business(connection)
        _insert_day(connection, business_id)
    with admin_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.current_business_id', '', true)"))
        visible = connection.execute(text("SELECT count(*) FROM operations.operational_days")).scalar_one()
        matched = connection.execute(
            text(
                """
                SELECT count(*) FROM identity.businesses
                WHERE id::text = current_setting('app.current_business_id', true)
                """
            )
        ).scalar_one()
    assert visible == 0
    assert matched == 0


def test_lumo_app_can_commit_a_valid_close(admin_engine) -> None:
    app_engine = _app_engine()
    try:
        with app_engine.begin() as connection:
            business_id = _insert_business(connection)
            closed = _close_pair(connection, business_id)
        with app_engine.begin() as connection:
            _tenant(connection, business_id)
            status = connection.execute(
                text("SELECT status FROM operations.operational_days WHERE id = :id"),
                {"id": closed["day_id"]},
            ).scalar_one()
        assert status == "closed"
    finally:
        app_engine.dispose()
        isolate_database_for_0007_downgrade(admin_engine)
