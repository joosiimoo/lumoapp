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
from sqlalchemy.exc import IntegrityError

from app.bootstrap.settings import Settings, get_settings
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.models import CashCountRow
from tests.conftest import DEFAULT_ADMIN_URL, DEFAULT_APP_URL, TEST_SECRET, postgres_available, settings_kwargs
from tests.sale_cleanup import isolate_database_for_0007_downgrade

BACKEND = Path(__file__).resolve().parents[1]
CONFIRMED_AT = datetime(2026, 1, 15, 18, 0, 0, tzinfo=UTC)
COUNTED_AT = datetime(2026, 1, 15, 23, 10, 0, tzinfo=UTC)


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


@pytest.fixture
def at_0005():
    settings = Settings.model_validate(settings_kwargs())
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = _engine()
    cfg = _config()
    command.upgrade(cfg, "head")
    isolate_database_for_0007_downgrade(engine)
    command.downgrade(cfg, "0005_operational_day")
    try:
        yield engine
    finally:
        command.upgrade(cfg, "head")
        engine.dispose()


@pytest.fixture
def at_head():
    settings = Settings.model_validate(settings_kwargs())
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = _engine()
    command.upgrade(_config(), "head")
    try:
        yield engine
    finally:
        engine.dispose()


def _tenant(connection, business_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.current_business_id', :business_id, true)"),
        {"business_id": str(business_id)},
    )


def _seed_day_with_cash_sale(connection) -> dict:
    business_id = new_uuid7()
    actor_id = new_uuid7()
    day_id = new_uuid7()
    session_id = new_uuid7()
    payment_id = new_uuid7()
    item_id = new_uuid7()
    product_id = new_uuid7()
    _tenant(connection, business_id)
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, 'Legacy close', 'MXN', 'America/Mexico_City', 'es-MX', 'active')
            """
        ),
        {"id": business_id},
    )
    connection.execute(
        text("INSERT INTO identity.users (id, business_id, name) VALUES (:id, :business_id, 'Owner')"),
        {"id": actor_id, "business_id": business_id},
    )
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
    connection.execute(
        text(
            """
            INSERT INTO operations.operational_days (
                id, business_id, business_date, status, timezone, created_at, updated_at
            ) VALUES (:id, :business_id, DATE '2026-01-15', 'open', 'America/Mexico_City', :at, :at)
            """
        ),
        {"id": day_id, "business_id": business_id, "at": CONFIRMED_AT},
    )
    connection.execute(
        text(
            """
            INSERT INTO sales.sale_sessions (
                id, business_id, actor_id, conversation_id, status, currency,
                operational_day_id, confirmed_at, created_at, updated_at
            ) VALUES (
                :id, :business_id, :actor_id, 'conv-legacy', 'confirmed', 'MXN',
                :day_id, :at, :at, :at
            )
            """
        ),
        {
            "id": session_id,
            "business_id": business_id,
            "actor_id": actor_id,
            "day_id": day_id,
            "at": CONFIRMED_AT,
        },
    )
    has_source_type = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'sales'
                  AND table_name = 'sale_items'
                  AND column_name = 'source_type'
            )
            """
        )
    ).scalar_one()
    has_snapshot = connection.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'sales'
                  AND table_name = 'sale_items'
                  AND column_name = 'catalog_unit_price_snapshot'
            )
            """
        )
    ).scalar_one()
    if has_source_type and has_snapshot:
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total, catalog_unit_price_snapshot, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :session_id, :product_id, 'catalog', 'Zanahoria',
                    1, 'kilogram', 1, 'kilogram', 25.00, 'MXN', 25.00, 25.00, :at, :at
                )
                """
            ),
            {
                "id": item_id,
                "business_id": business_id,
                "session_id": session_id,
                "product_id": product_id,
                "at": CONFIRMED_AT,
            },
        )
    elif has_source_type:
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, source_type, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :session_id, :product_id, 'catalog', 'Zanahoria',
                    1, 'kilogram', 1, 'kilogram', 25.00, 'MXN', 25.00, :at, :at
                )
                """
            ),
            {
                "id": item_id,
                "business_id": business_id,
                "session_id": session_id,
                "product_id": product_id,
                "at": CONFIRMED_AT,
            },
        )
    else:
        connection.execute(
            text(
                """
                INSERT INTO sales.sale_items (
                    id, business_id, sale_session_id, product_id, product_name_snapshot,
                    quantity_input, unit_input, quantity_normalized, unit_normalized,
                    unit_price, currency, line_total, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :session_id, :product_id, 'Zanahoria',
                    1, 'kilogram', 1, 'kilogram', 25.00, 'MXN', 25.00, :at, :at
                )
                """
            ),
            {
                "id": item_id,
                "business_id": business_id,
                "session_id": session_id,
                "product_id": product_id,
                "at": CONFIRMED_AT,
            },
        )
    connection.execute(
        text(
            """
            INSERT INTO sales.payments (
                id, business_id, sale_session_id, actor_id, method, amount, currency,
                status, source, created_at, updated_at
            ) VALUES (
                :id, :business_id, :session_id, :actor_id, 'cash', 25.00, 'MXN',
                'recorded', 'manual_capture', :at, :at
            )
            """
        ),
        {
            "id": payment_id,
            "business_id": business_id,
            "session_id": session_id,
            "actor_id": actor_id,
            "at": CONFIRMED_AT,
        },
    )
    return {
        "business_id": business_id,
        "actor_id": actor_id,
        "day_id": day_id,
        "session_id": session_id,
        "payment_id": payment_id,
    }


def _insert_count(connection, seeded: dict, *, amount: str, count_id: UUID | None = None) -> UUID:
    count_id = count_id or new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO operations.cash_counts (
                id, business_id, operational_day_id, actor_id, amount, currency, source,
                counted_at, created_at, updated_at
            ) VALUES (
                :id, :business_id, :day_id, :actor_id, :amount, 'MXN', 'manual_capture',
                :at, :at, :at
            )
            """
        ),
        {
            "id": count_id,
            "business_id": seeded["business_id"],
            "day_id": seeded["day_id"],
            "actor_id": seeded["actor_id"],
            "amount": Decimal(amount),
            "at": COUNTED_AT,
        },
    )
    return count_id


def test_upgrade_creates_cash_counts_and_keeps_existing_rows(at_0005) -> None:
    with at_0005.begin() as connection:
        assert connection.execute(
            text("SELECT to_regclass('operations.cash_counts') IS NULL")
        ).scalar_one()
        seeded = _seed_day_with_cash_sale(connection)
    command.upgrade(_config(), "head")
    assert _revision(at_0005) == "0010_work_items"
    business_id = seeded["business_id"]
    with at_0005.begin() as connection:
        _tenant(connection, business_id)
        session = connection.execute(
            text(
                """
                SELECT status, operational_day_id, confirmed_at
                FROM sales.sale_sessions WHERE id = :id
                """
            ),
            {"id": seeded["session_id"]},
        ).mappings().one()
        assert session["status"] == "confirmed"
        assert session["operational_day_id"] == seeded["day_id"]
        assert session["confirmed_at"] == CONFIRMED_AT
        payment = connection.execute(
            text("SELECT amount, method, status FROM sales.payments WHERE id = :id"),
            {"id": seeded["payment_id"]},
        ).mappings().one()
        assert Decimal(payment["amount"]) == Decimal("25.00")
        assert payment["method"] == "cash"
        day = connection.execute(
            text("SELECT status, business_date FROM operations.operational_days WHERE id = :id"),
            {"id": seeded["day_id"]},
        ).mappings().one()
        assert day["status"] == "open"
        assert day["business_date"].isoformat() == "2026-01-15"
        forced = connection.execute(
            text(
                """
                SELECT relrowsecurity, relforcerowsecurity
                FROM pg_class WHERE oid = 'operations.cash_counts'::regclass
                """
            )
        ).mappings().one()
        assert forced["relrowsecurity"] and forced["relforcerowsecurity"]
        policy = connection.execute(
            text(
                """
                SELECT polname FROM pg_policy
                WHERE polrelid = 'operations.cash_counts'::regclass
                """
            )
        ).scalars().all()
        assert policy == ["tenant_isolation"]
        indexdef = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_cash_counts_current'")
        ).scalar_one()
        assert "superseded_by_id IS NULL" in indexdef
        assert "UNIQUE" in indexdef

        first = _insert_count(connection, seeded, amount="20.00")
        assert first is not None
    with at_0005.connect() as connection:
        _tenant(connection, business_id)
        with pytest.raises(IntegrityError) as second_current:
            _insert_count(connection, seeded, amount="22.50")
        assert "uq_cash_counts_current" in str(second_current.value)
        connection.rollback()
        _tenant(connection, business_id)
        with pytest.raises(IntegrityError) as negative:
            _insert_count(connection, seeded, amount="-1.00")
        assert "ck_cash_counts_amount_non_negative" in str(negative.value)
        connection.rollback()

    isolate_database_for_0007_downgrade(at_0005)
    command.downgrade(_config(), "0005_operational_day")
    assert _revision(at_0005) == "0005_operational_day"
    with at_0005.begin() as connection:
        _tenant(connection, business_id)
        assert connection.execute(
            text("SELECT to_regclass('operations.cash_counts') IS NULL")
        ).scalar_one()
        assert connection.execute(
            text("SELECT count(*) FROM operations.operational_days WHERE business_id = :b"),
            {"b": business_id},
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT count(*) FROM sales.sale_sessions WHERE business_id = :b"),
            {"b": business_id},
        ).scalar_one() == 1
        assert connection.execute(
            text("SELECT count(*) FROM sales.payments WHERE business_id = :b"),
            {"b": business_id},
        ).scalar_one() == 1
    command.upgrade(_config(), "head")
    assert _revision(at_0005) == "0010_work_items"


def test_supersede_constraints_are_composite_and_correctly_deferred(at_head) -> None:
    with at_head.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT conname, condeferrable, condeferred, pg_get_constraintdef(oid) AS def
                FROM pg_constraint
                WHERE conrelid = 'operations.cash_counts'::regclass AND contype = 'f'
                """
            )
        ).mappings().all()
        by_name = {row["conname"]: row for row in rows}
        supersedes = by_name["fk_cash_counts_supersedes"]
        superseded_by = by_name["fk_cash_counts_superseded_by"]
        assert "FOREIGN KEY (supersedes_cash_count_id, business_id)" in supersedes["def"]
        assert "REFERENCES operations.cash_counts(id, business_id)" in supersedes["def"]
        assert supersedes["condeferrable"] is False
        assert supersedes["condeferred"] is False
        assert "FOREIGN KEY (superseded_by_id, business_id)" in superseded_by["def"]
        assert "REFERENCES operations.cash_counts(id, business_id)" in superseded_by["def"]
        assert superseded_by["condeferrable"] is True
        assert superseded_by["condeferred"] is True
        day = by_name["fk_cash_counts_operational_day"]
        assert "REFERENCES operations.operational_days(id, business_id)" in day["def"]
        indexdef = connection.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'uq_cash_counts_current'")
        ).scalar_one()
        assert indexdef.endswith("WHERE (superseded_by_id IS NULL)")
        deferrable_indexes = connection.execute(
            text(
                """
                SELECT conname, condeferrable FROM pg_constraint
                WHERE conrelid = 'operations.cash_counts'::regclass AND contype = 'u'
                """
            )
        ).mappings().all()
        assert all(row["condeferrable"] is False for row in deferrable_indexes)


def test_model_metadata_matches_the_migrated_deferral(at_head) -> None:
    by_name = {
        constraint.name: constraint
        for constraint in CashCountRow.__table__.constraints
        if constraint.name is not None
    }
    assert by_name["fk_cash_counts_superseded_by"].deferrable is True
    assert by_name["fk_cash_counts_superseded_by"].initially == "DEFERRED"
    assert not by_name["fk_cash_counts_supersedes"].deferrable
    with at_head.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT conname, condeferrable, condeferred FROM pg_constraint
                WHERE conrelid = 'operations.cash_counts'::regclass AND contype = 'f'
                """
            )
        ).mappings().all()
    database = {row["conname"]: (row["condeferrable"], row["condeferred"]) for row in rows}
    assert database["fk_cash_counts_superseded_by"] == (True, True)
    assert database["fk_cash_counts_supersedes"] == (False, False)


def test_recount_order_commits_and_a_dangling_link_fails_at_commit(at_head) -> None:
    with at_head.begin() as connection:
        seeded = _seed_day_with_cash_sale(connection)
    business_id = seeded["business_id"]
    previous_id = new_uuid7()
    new_id = new_uuid7()
    with at_head.begin() as connection:
        _tenant(connection, business_id)
        _insert_count(connection, seeded, amount="20.00", count_id=previous_id)
    with at_head.begin() as connection:
        _tenant(connection, business_id)
        connection.execute(
            text(
                """
                UPDATE operations.cash_counts SET superseded_by_id = :new_id
                WHERE id = :previous_id AND business_id = :business_id
                """
            ),
            {"new_id": new_id, "previous_id": previous_id, "business_id": business_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO operations.cash_counts (
                    id, business_id, operational_day_id, actor_id, amount, currency, source,
                    counted_at, supersedes_cash_count_id, created_at, updated_at
                ) VALUES (
                    :id, :business_id, :day_id, :actor_id, 22.50, 'MXN', 'manual_capture',
                    :at, :previous_id, :at, :at
                )
                """
            ),
            {
                "id": new_id,
                "business_id": business_id,
                "day_id": seeded["day_id"],
                "actor_id": seeded["actor_id"],
                "previous_id": previous_id,
                "at": COUNTED_AT,
            },
        )
    with at_head.connect() as connection:
        _tenant(connection, business_id)
        rows = connection.execute(
            text(
                """
                SELECT id, amount, supersedes_cash_count_id, superseded_by_id
                FROM operations.cash_counts WHERE business_id = :b ORDER BY amount
                """
            ),
            {"b": business_id},
        ).mappings().all()
        assert len(rows) == 2
        assert rows[0]["superseded_by_id"] == new_id
        assert rows[1]["supersedes_cash_count_id"] == previous_id
        assert rows[1]["superseded_by_id"] is None

        # The deferred constraint lets the UPDATE succeed and only rejects at COMMIT.
        _tenant(connection, business_id)
        connection.execute(
            text(
                """
                UPDATE operations.cash_counts SET superseded_by_id = :ghost
                WHERE id = :id AND business_id = :business_id
                """
            ),
            {"ghost": new_uuid7(), "id": new_id, "business_id": business_id},
        )
        with pytest.raises(IntegrityError) as dangling:
            connection.commit()
        assert "fk_cash_counts_superseded_by" in str(dangling.value)
        connection.rollback()
        _tenant(connection, business_id)
        still = connection.execute(
            text(
                """
                SELECT count(*) FROM operations.cash_counts
                WHERE business_id = :b AND superseded_by_id IS NULL
                """
            ),
            {"b": business_id},
        ).scalar_one()
        assert still == 1


def test_supersede_link_cannot_cross_tenants(at_head) -> None:
    with at_head.begin() as connection:
        carrota = _seed_day_with_cash_sale(connection)
    with at_head.begin() as connection:
        other = _seed_day_with_cash_sale(connection)
    carrota_count = new_uuid7()
    other_count = new_uuid7()
    with at_head.begin() as connection:
        _tenant(connection, carrota["business_id"])
        _insert_count(connection, carrota, amount="20.00", count_id=carrota_count)
    with at_head.begin() as connection:
        _tenant(connection, other["business_id"])
        _insert_count(connection, other, amount="30.00", count_id=other_count)

    # The tenant is set to Carrota, so RLS permits writing this row: the only thing that can
    # reject the cross-tenant link is the composite foreign key on (column, business_id).
    for column in ("supersedes_cash_count_id", "superseded_by_id"):
        with at_head.connect() as connection:
            _tenant(connection, carrota["business_id"])
            visible = connection.execute(
                text(
                    """
                    SELECT count(*) FROM operations.cash_counts
                    WHERE id = :id AND business_id = :business_id
                    """
                ),
                {"id": carrota_count, "business_id": carrota["business_id"]},
            ).scalar_one()
            assert visible == 1, "RLS must allow this row so the FK is the observed failure"
            with pytest.raises(IntegrityError) as crossed:
                connection.execute(
                    text(
                        f"""
                        UPDATE operations.cash_counts SET {column} = :other
                        WHERE id = :id AND business_id = :business_id
                        """
                    ),
                    {
                        "other": other_count,
                        "id": carrota_count,
                        "business_id": carrota["business_id"],
                    },
                )
                connection.commit()
            assert crossed.value.orig.sqlstate == "23503"
            assert "cash_counts" in str(crossed.value)
            connection.rollback()

    with at_head.connect() as connection:
        _tenant(connection, carrota["business_id"])
        links = connection.execute(
            text(
                """
                SELECT supersedes_cash_count_id, superseded_by_id
                FROM operations.cash_counts WHERE business_id = :b
                """
            ),
            {"b": carrota["business_id"]},
        ).mappings().all()
        assert all(row["supersedes_cash_count_id"] is None for row in links)
        assert all(row["superseded_by_id"] is None for row in links)
