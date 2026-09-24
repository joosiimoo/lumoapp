from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.bootstrap.settings import get_settings
from app.domain.shared.ids import new_uuid7
from tests.conftest import DEFAULT_ADMIN_URL, DEFAULT_APP_URL, TEST_SECRET, postgres_available, settings_kwargs
from tests.sale_cleanup import isolate_database_for_0007_downgrade
from app.bootstrap.settings import Settings

BACKEND = Path(__file__).resolve().parents[1]
T1 = datetime(2026, 1, 15, 18, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 1, 16, 5, 59, 59, tzinfo=UTC)
T3 = datetime(2026, 1, 16, 6, 0, 0, tzinfo=UTC)


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


def _revision(engine) -> str | None:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _uuid7_time(value: UUID) -> datetime:
    unix_ms = value.int >> 80
    return datetime.fromtimestamp(unix_ms / 1000, tz=UTC)


@pytest.fixture
def admin_engine():
    settings = Settings.model_validate(settings_kwargs())
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = _engine()
    cfg = _config()
    command.upgrade(cfg, "head")
    isolate_database_for_0007_downgrade(engine)
    command.downgrade(cfg, "0004_confirmed_payment")
    try:
        yield engine
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()


def _insert_legacy(connection, *, timezone_name: str) -> dict:
    business_id = new_uuid7()
    actor_id = new_uuid7()
    connection.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, 'Legacy', 'MXN', :timezone, 'es-MX', 'active')
            """
        ),
        {"id": business_id, "timezone": timezone_name},
    )
    connection.execute(
        text(
            """
            INSERT INTO identity.users (id, business_id, name)
            VALUES (:id, :business_id, 'Owner')
            """
        ),
        {"id": actor_id, "business_id": business_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO identity.memberships (id, business_id, user_id, role)
            VALUES (:id, :business_id, :user_id, 'owner')
            """
        ),
        {"id": new_uuid7(), "business_id": business_id, "user_id": actor_id},
    )
    product_id = new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO catalog.products (
                id, business_id, name, normalized_name, sale_unit, pricing_type, current_price, status
            ) VALUES (
                :id, :business_id, 'Zanahoria', 'zanahoria', 'kilogram', 'per_kilogram', 25.00, 'active'
            )
            """
        ),
        {"id": product_id, "business_id": business_id},
    )
    sessions = {
        "early": (new_uuid7(), "confirmed", T1, "conv-early"),
        "later": (new_uuid7(), "confirmed", T2, "conv-later"),
        "next": (new_uuid7(), "confirmed", T3, "conv-next"),
        "open": (new_uuid7(), "open", T1, "conv-open"),
        "ready": (new_uuid7(), "ready_to_charge", T2, "conv-ready"),
    }
    for key, (session_id, status, stamp, conversation_id) in sessions.items():
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_sessions (
                    id, business_id, actor_id, conversation_id, status, currency, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :actor_id, :conversation_id, :status, 'MXN', :created_at, :updated_at
                )
                """
            ),
            {
                "id": session_id,
                "business_id": business_id,
                "actor_id": actor_id,
                "conversation_id": conversation_id,
                "status": status,
                "created_at": stamp,
                "updated_at": stamp,
            },
        )
        if status == "confirmed":
            item_id = new_uuid7()
            payment_id = new_uuid7()
            connection.execute(
                text(
                    """
                    INSERT INTO sales.sale_items (
                        id, business_id, sale_session_id, product_id, product_name_snapshot,
                        quantity_input, unit_input, quantity_normalized, unit_normalized,
                        unit_price, currency, line_total, created_at, updated_at
                    ) VALUES (
                        :id, :business_id, :sale_session_id, :product_id, 'Zanahoria',
                        1, 'kilogram', 1, 'kilogram',
                        25.00, 'MXN', 25.00, :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": item_id,
                    "business_id": business_id,
                    "sale_session_id": session_id,
                    "product_id": product_id,
                    "created_at": stamp,
                    "updated_at": stamp,
                },
            )
            connection.execute(
                text(
                    """
                    INSERT INTO sales.payments (
                        id, business_id, sale_session_id, actor_id, method, amount, currency,
                        status, source, created_at, updated_at
                    ) VALUES (
                        :id, :business_id, :sale_session_id, :actor_id, 'cash', 25.00, 'MXN',
                        'recorded', 'manual_capture', :created_at, :updated_at
                    )
                    """
                ),
                {
                    "id": payment_id,
                    "business_id": business_id,
                    "sale_session_id": session_id,
                    "actor_id": actor_id,
                    "created_at": stamp,
                    "updated_at": stamp,
                },
            )
            sessions[key] = (session_id, status, stamp, conversation_id, item_id, payment_id)
    return {"business_id": business_id, "sessions": sessions}


def test_legacy_backfill_from_0004(admin_engine) -> None:
    with admin_engine.begin() as connection:
        seeded = _insert_legacy(connection, timezone_name="America/Mexico_City")
    command.upgrade(_config(), "head")
    assert _revision(admin_engine) == "0009_catalog_price_override"
    business_id = seeded["business_id"]
    with admin_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.current_business_id', :business_id, true)"),
            {"business_id": str(business_id)},
        )
        rows = connection.execute(
            text(
                """
                SELECT id, status, updated_at, confirmed_at, operational_day_id
                FROM sales.sale_sessions
                WHERE business_id = :business_id
                """
            ),
            {"business_id": business_id},
        ).mappings().all()
        by_id = {row["id"]: row for row in rows}
        early = by_id[seeded["sessions"]["early"][0]]
        later = by_id[seeded["sessions"]["later"][0]]
        nxt = by_id[seeded["sessions"]["next"][0]]
        opened = by_id[seeded["sessions"]["open"][0]]
        ready = by_id[seeded["sessions"]["ready"][0]]
        assert early["confirmed_at"] == T1
        assert later["confirmed_at"] == T2
        assert nxt["confirmed_at"] == T3
        assert early["updated_at"] == T1
        assert later["updated_at"] == T2
        assert opened["operational_day_id"] is None and opened["confirmed_at"] is None
        assert ready["operational_day_id"] is None and ready["confirmed_at"] is None
        assert early["operational_day_id"] == later["operational_day_id"]
        assert early["operational_day_id"] != nxt["operational_day_id"]
        days = connection.execute(
            text(
                """
                SELECT id, business_date, status, created_at, updated_at
                FROM operations.operational_days
                WHERE business_id = :business_id
                ORDER BY business_date
                """
            ),
            {"business_id": business_id},
        ).mappings().all()
        assert len(days) == 2
        first, second = days
        assert first["business_date"].isoformat() == "2026-01-15"
        assert second["business_date"].isoformat() == "2026-01-16"
        assert first["created_at"] == T1
        assert first["updated_at"] == T1
        assert second["created_at"] == T3
        assert second["updated_at"] == T3
        assert first["status"] == "open"
        assert abs((_uuid7_time(first["id"]) - T1).total_seconds()) > 3600
        payments = connection.execute(
            text("SELECT amount, updated_at FROM sales.payments WHERE business_id = :business_id"),
            {"business_id": business_id},
        ).mappings().all()
        assert len(payments) == 3
        assert {Decimal(row["amount"]) for row in payments} == {Decimal("25.00")}
        items = connection.execute(
            text("SELECT line_total FROM sales.sale_items WHERE business_id = :business_id"),
            {"business_id": business_id},
        ).scalars().all()
        assert {Decimal(item) for item in items} == {Decimal("25.00")}
        opened_audit = connection.execute(
            text(
                """
                SELECT count(*) FROM audit.audit_events
                WHERE business_id = :business_id AND action = 'operational_day.opened'
                """
            ),
            {"business_id": business_id},
        ).scalar_one()
        opened_outbox = connection.execute(
            text(
                """
                SELECT count(*) FROM platform.outbox_events
                WHERE business_id = :business_id AND event_type = 'operational_day.opened'
                """
            ),
            {"business_id": business_id},
        ).scalar_one()
        assert opened_audit == 0
        assert opened_outbox == 0
        membership = connection.execute(
            text(
                """
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_sale_sessions_day_membership'
                """
            )
        ).scalar_one()
        assert membership == 1
        forced = connection.execute(
            text(
                """
                SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE (n.nspname, c.relname) IN (
                    ('operations', 'operational_days'),
                    ('identity', 'businesses'),
                    ('sales', 'sale_sessions')
                )
                """
            )
        ).mappings().all()
        assert len(forced) == 3
        assert all(row["relrowsecurity"] and row["relforcerowsecurity"] for row in forced)
        indexdef = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_sale_sessions_active_context'")
        ).scalar_one()
        assert "confirmed" not in indexdef


def test_invalid_timezone_fails_upgrade_and_stays_at_0004(admin_engine) -> None:
    with admin_engine.begin() as connection:
        _insert_legacy(connection, timezone_name="Not/AZone")
    with pytest.raises(Exception):
        command.upgrade(_config(), "head")
    assert _revision(admin_engine) == "0004_confirmed_payment"
    with admin_engine.begin() as connection:
        connection.execute(text("ALTER TABLE identity.businesses DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("UPDATE identity.businesses SET timezone = 'America/Mexico_City' WHERE timezone = 'Not/AZone'"))
        connection.execute(text("ALTER TABLE identity.businesses ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE identity.businesses FORCE ROW LEVEL SECURITY"))
