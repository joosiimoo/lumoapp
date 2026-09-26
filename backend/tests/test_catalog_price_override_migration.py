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
from tests.sale_cleanup import discard_work_items

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


def _revision(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


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
            VALUES (:id, 'Override fixture', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
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
                :id, :business_id, 'Tomate', 'tomate', 'kilogram', 'per_kilogram', 20.00, 'active'
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


def _insert_line(connection, **values) -> UUID:
    item_id = new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO sales.sale_items (
                id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                quantity_input, unit_input, quantity_normalized, unit_normalized,
                unit_price, currency, line_total, catalog_unit_price_snapshot, price_override_reason
            ) VALUES (
                :id, :business_id, :session_id, :product_id, :source_type, :name,
                1, 'kilogram', 1, 'kilogram', :unit_price, 'MXN', :line_total,
                :snapshot, :reason
            )
            """
        ),
        {"id": item_id, **values},
    )
    return item_id


def _clear_overrides(engine) -> None:
    discard_work_items(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
        connection.execute(
            text(
                """
                DELETE FROM sales.sale_items
                WHERE source_type = 'catalog'
                  AND (
                    price_override_reason IS NOT NULL
                    OR catalog_unit_price_snapshot IS DISTINCT FROM unit_price
                  )
                """
            )
        )
        connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))


def test_upgrade_backfills_catalog_and_free_concept_and_keeps_rls(migrated) -> None:
    _clear_overrides(migrated)
    command.downgrade(_config(), "0008_noncatalog_sale_item")
    with migrated.begin() as connection:
        business_id = _business(connection)
        product_id = _product(connection, business_id)
        session_id = _session(connection, business_id)
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total
                ) VALUES (
                    :id, :business_id, :session_id, :product_id, 'catalog', 'Tomate',
                    1, 'kilogram', 1, 'kilogram', 20.00, 'MXN', 20.00
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
                    :id, :business_id, :session_id, NULL, 'free_concept', 'hielo',
                    2, 'package', 2, 'package', 18.00, 'MXN', 36.00
                )
                """
            ),
            {"id": free_id, "business_id": business_id, "session_id": session_id},
        )
    command.upgrade(_config(), "0009_catalog_price_override")
    assert _revision(migrated) == "0009_catalog_price_override"
    with migrated.begin() as connection:
        forced = connection.execute(
            text(
                """
                SELECT c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'sales' AND c.relname = 'sale_items'
                """
            )
        ).one()
        assert forced.relrowsecurity is True
        assert forced.relforcerowsecurity is True
        connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
        catalog = connection.execute(
            text(
                """
                SELECT catalog_unit_price_snapshot, price_override_reason
                FROM sales.sale_items
                WHERE source_type = 'catalog' AND business_id = :business_id
                """
            ),
            {"business_id": business_id},
        ).one()
        free = connection.execute(
            text(
                """
                SELECT catalog_unit_price_snapshot, price_override_reason, unit_price
                FROM sales.sale_items WHERE id = :id
                """
            ),
            {"id": free_id},
        ).one()
        assert catalog.catalog_unit_price_snapshot == 20
        assert catalog.price_override_reason is None
        assert free.catalog_unit_price_snapshot is None
        assert free.price_override_reason is None
        assert free.unit_price == 18
        check = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conname = 'ck_sale_items_catalog_price'
                """
            )
        ).scalar_one()
        assert "price_override_reason" in check
        roles = {
            row.rolname: row.rolbypassrls
            for row in connection.execute(
                text("SELECT rolname, rolbypassrls FROM pg_roles WHERE rolname IN ('lumo_admin', 'lumo_app')")
            )
        }
        assert roles["lumo_admin"] is False
        assert roles["lumo_app"] is False
        policy = connection.execute(
            text(
                """
                SELECT qual::text
                FROM pg_policies
                WHERE schemaname = 'sales' AND tablename = 'sale_items' AND policyname = 'tenant_isolation'
                """
            )
        ).scalar_one()
        assert "app.current_business_id" in policy
        nested = connection.begin_nested()
        try:
            connection.execute(
                text(
                    """
                    INSERT INTO sales.sale_items (
                        id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                        quantity_input, unit_input, quantity_normalized, unit_normalized,
                        unit_price, currency, line_total
                    ) VALUES (
                        :id, :business_id, :session_id, :product_id, 'catalog', 'Tomate',
                        1, 'kilogram', 1, 'kilogram', 20.00, 'MXN', 20.00
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
            nested.commit()
            raise AssertionError("catalog row without a snapshot was accepted")
        except IntegrityError:
            nested.rollback()
        connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))


def test_catalog_only_downgrade_succeeds(migrated) -> None:
    _clear_overrides(migrated)
    with migrated.begin() as connection:
        business_id = _business(connection)
        product_id = _product(connection, business_id)
        session_id = _session(connection, business_id)
        _insert_line(
            connection,
            business_id=business_id,
            session_id=session_id,
            product_id=product_id,
            source_type="catalog",
            name="Tomate",
            unit_price=20,
            line_total=20,
            snapshot=20,
            reason=None,
        )
    discard_work_items(migrated)
    command.downgrade(_config(), "0008_noncatalog_sale_item")
    assert _revision(migrated) == "0008_noncatalog_sale_item"
    command.upgrade(_config(), "head")


def test_free_concept_does_not_block_downgrade_and_survives(migrated) -> None:
    _clear_overrides(migrated)
    with migrated.begin() as connection:
        business_id = _business(connection)
        product_id = _product(connection, business_id)
        session_id = _session(connection, business_id)
        _insert_line(
            connection,
            business_id=business_id,
            session_id=session_id,
            product_id=product_id,
            source_type="catalog",
            name="Tomate",
            unit_price=20,
            line_total=20,
            snapshot=20,
            reason=None,
        )
        free_id = _insert_line(
            connection,
            business_id=business_id,
            session_id=session_id,
            product_id=None,
            source_type="free_concept",
            name="hielo",
            unit_price=18,
            line_total=36,
            snapshot=None,
            reason=None,
        )
    discard_work_items(migrated)
    command.downgrade(_config(), "0008_noncatalog_sale_item")
    assert _revision(migrated) == "0008_noncatalog_sale_item"
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
        row = connection.execute(
            text(
                """
                SELECT source_type, product_id, product_name_snapshot, unit_price, line_total
                FROM sales.sale_items WHERE id = :id
                """
            ),
            {"id": free_id},
        ).one()
        connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))
    assert row.source_type == "free_concept"
    assert row.product_id is None
    assert row.product_name_snapshot == "hielo"
    assert row.unit_price == 18
    assert row.line_total == 36
    command.upgrade(_config(), "head")


def test_catalog_override_blocks_downgrade_without_deleting_rows(migrated) -> None:
    with migrated.begin() as connection:
        business_id = _business(connection)
        product_id = _product(connection, business_id)
        session_id = _session(connection, business_id)
        item_id = _insert_line(
            connection,
            business_id=business_id,
            session_id=session_id,
            product_id=product_id,
            source_type="catalog",
            name="Tomate",
            unit_price=30,
            line_total=27,
            snapshot=20,
            reason="precio especial para cliente",
        )
    discard_work_items(migrated)
    with pytest.raises(Exception, match="cannot downgrade 0009 while a catalog price override exists"):
        command.downgrade(_config(), "0008_noncatalog_sale_item")
    assert _revision(migrated) == "0012_source_coverage_event_memory"
    with migrated.begin() as connection:
        connection.execute(text("ALTER TABLE sales.sale_items DISABLE ROW LEVEL SECURITY"))
        kept = connection.execute(
            text("SELECT unit_price, catalog_unit_price_snapshot, price_override_reason FROM sales.sale_items WHERE id = :id"),
            {"id": item_id},
        ).one()
        connection.execute(text("ALTER TABLE sales.sale_items ENABLE ROW LEVEL SECURITY"))
        connection.execute(text("ALTER TABLE sales.sale_items FORCE ROW LEVEL SECURITY"))
    assert kept.unit_price == 30
    assert kept.catalog_unit_price_snapshot == 20
    assert kept.price_override_reason == "precio especial para cliente"
