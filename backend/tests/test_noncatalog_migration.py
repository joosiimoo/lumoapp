from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

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


def _app_engine():
    return create_engine(Settings.model_validate(settings_kwargs()).sqlalchemy_url)


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


def _tenant(connection, business_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )


def _business(connection) -> UUID:
    business_id = new_uuid7()
    _tenant(connection, business_id)
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, 'Free concept fixture', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
            """
        ),
        {"id": business_id},
    )
    return business_id


def _product(connection, business_id: UUID) -> UUID:
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
    return product_id


def _session(connection, business_id: UUID) -> UUID:
    session_id = new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO sales.sale_sessions (id, business_id, actor_id, status, currency)
            VALUES (:id, :business_id, :actor_id, 'open', 'MXN')
            """
        ),
        {"id": session_id, "business_id": business_id, "actor_id": new_uuid7()},
    )
    return session_id


def test_upgrade_backfills_catalog_and_enforces_checks(migrated) -> None:
    assert _revision(migrated) == "0009_catalog_price_override"
    with migrated.begin() as connection:
        roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('lumo_admin', 'lumo_app')")
            )
        }
        assert roles["lumo_admin"] is False
        assert roles["lumo_app"] is False
        forced = connection.execute(
            text(
                """
                SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'sales' AND c.relname = 'sale_items'
                """
            )
        ).one()
        assert forced.relrowsecurity is True
        assert forced.relforcerowsecurity is True
        business_id = _business(connection)
        product_id = _product(connection, business_id)
        session_id = _session(connection, business_id)
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total, catalog_unit_price_snapshot
                ) VALUES (
                    :id, :business_id, :session_id, :product_id, 'catalog', 'Zanahoria',
                    1, 'unit', 1, 'unit', 25.00, 'MXN', 25.00, 25.00
                )
                """
            ),
            {
                "id": new_uuid7(),
                "business_id": business_id,
                "session_id": session_id,
                "product_id": product_id,
            },
        )
        free_id = new_uuid7()
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total
                ) VALUES (
                    :id, :business_id, :session_id, NULL, 'free_concept', 'Café Orgánico',
                    1, 'unit', 1, 'unit', 50.00, 'MXN', 50.00
                )
                """
            ),
            {"id": free_id, "business_id": business_id, "session_id": session_id},
        )
        other = _business(connection)
        other_product = _product(connection, other)
    with migrated.connect() as connection:
        transaction = connection.begin()
        try:
            _tenant(connection, business_id)
            connection.execute(
                text(
                    """
                    INSERT INTO sales.sale_items (
                        id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                        quantity_input, unit_input, quantity_normalized, unit_normalized,
                        unit_price, currency, line_total, catalog_unit_price_snapshot
                    ) VALUES (
                        :id, :business_id, :session_id, :product_id, 'catalog', 'Zanahoria',
                        1, 'unit', 1, 'unit', 25.00, 'MXN', 25.00, 25.00
                    )
                    """
                ),
                {
                    "id": new_uuid7(),
                    "business_id": business_id,
                    "session_id": session_id,
                    "product_id": other_product,
                },
            )
            transaction.rollback()
            raise AssertionError("cross-tenant product id was accepted")
        except IntegrityError:
            transaction.rollback()
    app = _app_engine()
    try:
        with app.connect() as connection:
            _tenant(connection, other)
            seen = connection.execute(text("SELECT id FROM sales.sale_items")).all()
            assert free_id not in {row.id for row in seen}
    finally:
        app.dispose()
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
        connection.execute(text("DELETE FROM sales.sale_items WHERE id = :id"), {"id": free_id})
        connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))


def test_downgrade_refuses_free_concept_and_accepts_catalog_only(migrated) -> None:
    from tests.test_catalog_price_override_migration import _clear_overrides

    _clear_overrides(migrated)
    engine = migrated
    with engine.begin() as connection:
        business_id = _business(connection)
        session_id = _session(connection, business_id)
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total
                ) VALUES (
                    :id, :business_id, :session_id, NULL, 'free_concept', 'hielo',
                    2, 'package', 2, 'package', 18.00, 'MXN', 36.00
                )
                """
            ),
            {"id": new_uuid7(), "business_id": business_id, "session_id": session_id},
        )
    with pytest.raises(Exception, match="free-concept"):
        command.downgrade(_config(), "0007_daily_close_confirmation")
    assert _revision(engine) == "0009_catalog_price_override"
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
        kept = connection.execute(text("SELECT count(*) FROM sales.sale_items WHERE source_type = 'free_concept'")).scalar_one()
        connection.execute(text("DELETE FROM sales.sale_items WHERE source_type = 'free_concept'"))
        connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))
    assert kept >= 1
    command.downgrade(_config(), "0007_daily_close_confirmation")
    assert _revision(engine) == "0007_daily_close_confirmation"
    command.upgrade(_config(), "head")
    assert _revision(engine) == "0009_catalog_price_override"


def _revision(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
