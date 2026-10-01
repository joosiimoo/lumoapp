"""Base→head proof for 0018_transaction_references on a disposable database.

Covers CHECK/backfill ordering, deterministic per-business numbering, enriched Event Memory
facts, initialized counters, RLS/FORCE RLS, final constraints, and a clean downgrade.
"""

from __future__ import annotations

import json
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
from tests.conftest import TEST_SECRET, postgres_available, settings_kwargs
from tests.migration_db import CLEAN_PROOF_0018_DB_NAME, use_clean_proof_database

BACKEND = Path(__file__).resolve().parents[1]
PREVIOUS = "0017_closing_snapshot_close_note"
HEAD = "0018_transaction_references"

pytestmark = pytest.mark.schema_migration

T1 = datetime(2026, 9, 22, 10, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 22, 11, 0, tzinfo=UTC)
T3 = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
T4 = datetime(2026, 9, 22, 18, 0, tzinfo=UTC)
T0 = datetime(2026, 9, 22, 5, 0, tzinfo=UTC)

S1 = UUID("00000000-0000-7000-8000-000000000001")
S2 = UUID("00000000-0000-7000-8000-000000000002")
S3 = UUID("00000000-0000-7000-8000-000000000003")
S4 = UUID("00000000-0000-7000-8000-000000000004")
S5 = UUID("00000000-0000-7000-8000-000000000005")


def _config() -> Config:
    os.environ.setdefault("APP_ENV", "test")
    os.environ.setdefault("DEV_TOKEN_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    return cfg


def _admin_engine():
    return create_engine(Settings.model_validate(settings_kwargs()).sqlalchemy_admin_url)


def _app_engine():
    return create_engine(Settings.model_validate(settings_kwargs()).sqlalchemy_url)


def _revision(engine) -> str:
    with engine.connect() as connection:
        return connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()


def _tenant(connection, business_id: UUID) -> None:
    connection.execute(
        text("SELECT set_config('app.current_business_id', :id, true)"),
        {"id": str(business_id)},
    )


def _seed_business(connection, name: str) -> tuple[UUID, UUID, UUID]:
    business_id, actor_id, day_id = new_uuid7(), new_uuid7(), new_uuid7()
    _tenant(connection, business_id)
    connection.execute(
        text(
            """
            INSERT INTO identity.businesses (id, name, currency, timezone, locale, status)
            VALUES (:id, :name, 'MXN', 'America/Mexico_City', 'es-MX', 'active')
            """
        ),
        {"id": business_id, "name": name},
    )
    connection.execute(
        text("INSERT INTO identity.users (id, business_id, name) VALUES (:id, :b, 'Owner')"),
        {"id": actor_id, "b": business_id},
    )
    connection.execute(
        text(
            """
            INSERT INTO operations.operational_days (
                id, business_id, business_date, status, timezone, created_at, updated_at
            ) VALUES (:id, :b, DATE '2026-09-22', 'open', 'America/Mexico_City', :at, :at)
            """
        ),
        {"id": day_id, "b": business_id, "at": T1},
    )
    return business_id, actor_id, day_id


def _seed_sale(
    connection,
    *,
    business_id: UUID,
    actor_id: UUID,
    day_id: UUID,
    session_id: UUID,
    confirmed_at: datetime,
    voided_at: datetime | None = None,
) -> None:
    status = "voided" if voided_at is not None else "confirmed"
    connection.execute(
        text(
            """
            INSERT INTO sales.sale_sessions (
                id, business_id, actor_id, conversation_id, status, currency,
                operational_day_id, confirmed_at, sale_revision,
                voided_at, voided_by_actor_id, void_reason
            ) VALUES (
                :id, :b, :actor, 'conv', :status, 'MXN',
                :day, :confirmed_at, 1,
                :voided_at, :void_actor, :void_reason
            )
            """
        ),
        {
            "id": session_id,
            "b": business_id,
            "actor": actor_id,
            "status": status,
            "day": day_id,
            "confirmed_at": confirmed_at,
            "voided_at": voided_at,
            "void_actor": actor_id if voided_at else None,
            "void_reason": "cobro duplicado" if voided_at else None,
        },
    )
    _seed_event(
        connection,
        business_id=business_id,
        day_id=day_id,
        event_type="sale_confirmed",
        entity_type="sale_session",
        entity_id=session_id,
        occurred_at=confirmed_at,
        facts={
            "sale_session_id": str(session_id),
            "payment_id": str(new_uuid7()),
            "payment_method": "cash",
            "amount": "10.00",
            "currency": "MXN",
        },
    )
    if voided_at is not None:
        _seed_event(
            connection,
            business_id=business_id,
            day_id=day_id,
            event_type="sale_voided",
            entity_type="sale_session",
            entity_id=session_id,
            occurred_at=voided_at,
            facts={
                "sale_session_id": str(session_id),
                "payment_id": str(new_uuid7()),
                "payment_method": "cash",
                "amount": "10.00",
                "currency": "MXN",
                "void_reason": "cobro duplicado",
                "voided_by_actor_id": str(actor_id),
            },
        )


def _seed_event(
    connection,
    *,
    business_id: UUID,
    day_id: UUID,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    occurred_at: datetime,
    facts: dict,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO operations.business_events (
                id, business_id, operational_day_id, event_type, occurred_at,
                source_type, source_entity_type, source_entity_id, facts, created_at
            ) VALUES (
                :id, :b, :day, :event_type, :at,
                'manual_capture', :entity_type, :entity_id, CAST(:facts AS jsonb), :at
            )
            """
        ),
        {
            "id": new_uuid7(),
            "b": business_id,
            "day": day_id,
            "event_type": event_type,
            "at": occurred_at,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "facts": json.dumps(facts),
        },
    )


def _seed_close(connection, *, business_id: UUID, actor_id: UUID, day_id: UUID) -> tuple[UUID, UUID]:
    count_id, snapshot_id = new_uuid7(), new_uuid7()
    connection.execute(
        text(
            """
            INSERT INTO operations.cash_counts (
                id, business_id, operational_day_id, actor_id, amount, currency, source,
                counted_at, created_at, updated_at
            ) VALUES (:id, :b, :day, :actor, 22.50, 'MXN', 'manual_capture', :at, :at, :at)
            """
        ),
        {"id": count_id, "b": business_id, "day": day_id, "actor": actor_id, "at": T4},
    )
    connection.execute(
        text(
            """
            INSERT INTO operations.closing_snapshots (
                id, business_id, operational_day_id, cash_count_id, actor_id, business_date,
                currency, sale_count, gross_sales_total, cash_total, card_total, transfer_total,
                expected_cash, counted_cash, cash_difference, cash_status,
                closed_at, created_at, updated_at, close_note
            ) VALUES (
                :id, :b, :day, :count, :actor, DATE '2026-09-22',
                'MXN', 3, 22.50, 22.50, 0, 0,
                22.50, 22.50, 0, 'balanced', :at, :at, :at, 'todo bien'
            )
            """
        ),
        {"id": snapshot_id, "b": business_id, "day": day_id, "count": count_id, "actor": actor_id, "at": T4},
    )
    connection.execute(
        text("UPDATE operations.operational_days SET status = 'closed', updated_at = :at WHERE id = :id"),
        {"id": day_id, "at": T4},
    )
    _seed_event(
        connection,
        business_id=business_id,
        day_id=day_id,
        event_type="cash_count_recorded",
        entity_type="cash_count",
        entity_id=count_id,
        occurred_at=T4,
        facts={
            "cash_count_id": str(count_id),
            "expected_cash": "22.50",
            "counted_cash": "22.50",
            "cash_difference": "0.00",
            "cash_status": "balanced",
            "currency": "MXN",
        },
    )
    _seed_event(
        connection,
        business_id=business_id,
        day_id=day_id,
        event_type="daily_close_completed",
        entity_type="closing_snapshot",
        entity_id=snapshot_id,
        occurred_at=T4,
        facts={
            "outcome_run_id": str(new_uuid7()),
            "closing_snapshot_id": str(snapshot_id),
            "sale_count": 3,
            "gross_sales_total": "22.50",
            "expected_cash": "22.50",
            "counted_cash": "22.50",
            "cash_difference": "0.00",
            "cash_status": "balanced",
            "currency": "MXN",
            "close_note": "todo bien",
        },
    )
    return count_id, snapshot_id


def _event_facts(connection, business_id: UUID, event_type: str, entity_id: UUID) -> dict:
    _tenant(connection, business_id)
    return connection.execute(
        text(
            """
            SELECT facts FROM operations.business_events
            WHERE business_id = :b AND event_type = :t AND source_entity_id = :e
            """
        ),
        {"b": business_id, "t": event_type, "e": entity_id},
    ).scalar_one()


def _sequences(connection, business_id: UUID) -> dict[UUID, tuple[int | None, int | None]]:
    _tenant(connection, business_id)
    return {
        row[0]: (row[1], row[2])
        for row in connection.execute(
            text(
                "SELECT id, transaction_sequence, void_transaction_sequence "
                "FROM sales.sale_sessions WHERE business_id = :b"
            ),
            {"b": business_id},
        ).fetchall()
    }


def test_0018_applies_cleanly_from_base_with_expected_schema() -> None:
    if not postgres_available(Settings.model_validate(settings_kwargs())):
        pytest.skip("PostgreSQL is not available")

    with use_clean_proof_database(CLEAN_PROOF_0018_DB_NAME):
        command.upgrade(_config(), "head")
        admin = _admin_engine()
        try:
            assert _revision(admin) == HEAD
            with admin.connect() as connection:
                rls = connection.execute(
                    text(
                        """
                        SELECT c.relrowsecurity, c.relforcerowsecurity
                        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = 'operations' AND c.relname = 'business_transaction_counters'
                        """
                    )
                ).one()
                assert tuple(rls) == (True, True)
                policy = connection.execute(
                    text(
                        """
                        SELECT polname, pg_get_expr(polqual, polrelid)
                        FROM pg_policy
                        WHERE polrelid = 'operations.business_transaction_counters'::regclass
                        """
                    )
                ).one()
                assert policy[0] == "tenant_isolation"
                assert "app.current_business_id" in policy[1]
                grants = {
                    row[0]
                    for row in connection.execute(
                        text(
                            """
                            SELECT privilege_type FROM information_schema.role_table_grants
                            WHERE table_schema = 'operations'
                              AND table_name = 'business_transaction_counters'
                              AND grantee = 'lumo_app'
                            """
                        )
                    )
                }
                assert {"SELECT", "INSERT", "UPDATE"} <= grants
                names = {
                    row[0]
                    for row in connection.execute(
                        text(
                            """
                            SELECT conname FROM pg_constraint
                            WHERE conname IN (
                                'ck_sale_sessions_transaction_sequences',
                                'ck_sale_sessions_void_transaction_sequence',
                                'uq_closing_snapshots_business_transaction_sequence',
                                'ck_business_events_shape'
                            )
                            """
                        )
                    )
                }
                assert names == {
                    "ck_sale_sessions_transaction_sequences",
                    "ck_sale_sessions_void_transaction_sequence",
                    "uq_closing_snapshots_business_transaction_sequence",
                    "ck_business_events_shape",
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        text(
                            "SELECT indexname FROM pg_indexes WHERE schemaname = 'sales' "
                            "AND tablename = 'sale_sessions'"
                        )
                    )
                }
                assert "uq_sale_sessions_business_transaction_sequence" in indexes
                assert "uq_sale_sessions_business_void_transaction_sequence" in indexes
                shape = connection.execute(
                    text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_business_events_shape'")
                ).scalar_one()
                assert shape.count("transaction_number") >= 3
                assert "original_transaction_number" in shape
                nullable = connection.execute(
                    text(
                        """
                        SELECT table_name, column_name, is_nullable FROM information_schema.columns
                        WHERE column_name IN ('transaction_sequence', 'void_transaction_sequence')
                          AND table_schema IN ('sales', 'operations')
                        """
                    )
                ).fetchall()
                assert {(r[0], r[1]): r[2] for r in nullable} == {
                    ("sale_sessions", "transaction_sequence"): "YES",
                    ("sale_sessions", "void_transaction_sequence"): "YES",
                    ("closing_snapshots", "transaction_sequence"): "NO",
                }
        finally:
            admin.dispose()


def test_0018_backfills_deterministically_and_downgrades_cleanly() -> None:
    if not postgres_available(Settings.model_validate(settings_kwargs())):
        pytest.skip("PostgreSQL is not available")

    with use_clean_proof_database(CLEAN_PROOF_0018_DB_NAME):
        cfg = _config()
        command.upgrade(cfg, PREVIOUS)
        admin = _admin_engine()
        app = _app_engine()
        try:
            assert _revision(admin) == PREVIOUS
            with admin.begin() as connection:
                a_id, a_actor, a_day = _seed_business(connection, "A")
                for session_id, confirmed, voided in (
                    (S1, T1, None),
                    (S3, T1, None),  # same instant as S1: entity id breaks the tie
                    (S2, T2, T3),
                    (S4, T3, None),  # same instant as S2's void: sale sorts before void
                ):
                    _seed_sale(
                        connection,
                        business_id=a_id,
                        actor_id=a_actor,
                        day_id=a_day,
                        session_id=session_id,
                        confirmed_at=confirmed,
                        voided_at=voided,
                    )
                _count_id, snapshot_id = _seed_close(
                    connection, business_id=a_id, actor_id=a_actor, day_id=a_day
                )
            with admin.begin() as connection:
                b_id, b_actor, b_day = _seed_business(connection, "B")
                _seed_sale(
                    connection,
                    business_id=b_id,
                    actor_id=b_actor,
                    day_id=b_day,
                    session_id=S5,
                    confirmed_at=T0,
                )
            with admin.begin() as connection:
                c_id, _c_actor, _c_day = _seed_business(connection, "C empty")

            command.upgrade(cfg, "head")
            assert _revision(admin) == HEAD

            with admin.connect() as connection:
                sequences = _sequences(connection, a_id)
                assert sequences == {
                    S1: (1, None),
                    S3: (2, None),
                    S2: (3, 5),
                    S4: (4, None),
                }
                _tenant(connection, a_id)
                assert connection.execute(
                    text("SELECT transaction_sequence FROM operations.closing_snapshots WHERE id = :id"),
                    {"id": snapshot_id},
                ).scalar_one() == 6
                # Per-business numbering: B starts again at 1.
                assert _sequences(connection, b_id) == {S5: (1, None)}

                # Event Memory enrichment (migration-only).
                assert _event_facts(connection, a_id, "sale_confirmed", S1)["transaction_number"] == "TRX-000001"
                assert _event_facts(connection, a_id, "sale_confirmed", S2)["transaction_number"] == "TRX-000003"
                void_facts = _event_facts(connection, a_id, "sale_voided", S2)
                assert void_facts["transaction_number"] == "TRX-000005"
                assert void_facts["original_transaction_number"] == "TRX-000003"
                assert void_facts["void_reason"] == "cobro duplicado"
                close_facts = _event_facts(connection, a_id, "daily_close_completed", snapshot_id)
                assert close_facts["transaction_number"] == "TRX-000006"
                assert close_facts["close_note"] == "todo bien"
                cash_facts = connection.execute(
                    text(
                        "SELECT facts FROM operations.business_events "
                        "WHERE business_id = :b AND event_type = 'cash_count_recorded'"
                    ),
                    {"b": a_id},
                ).scalar_one()
                assert set(cash_facts) == {
                    "cash_count_id",
                    "expected_cash",
                    "counted_cash",
                    "cash_difference",
                    "cash_status",
                    "currency",
                }
                assert _event_facts(connection, b_id, "sale_confirmed", S5)["transaction_number"] == "TRX-000001"

                # Counters: max assigned sequence; empty businesses start at 0.
                values = {}
                for business_id in (a_id, b_id, c_id):
                    _tenant(connection, business_id)
                    values[business_id] = connection.execute(
                        text("SELECT last_value FROM operations.business_transaction_counters")
                    ).scalar_one()
                assert values == {a_id: 6, b_id: 1, c_id: 0}

                # RLS lets a tenant see only its own counter. Events stay immutable after the migration.
                with pytest.raises(Exception, match="business events are immutable"):
                    with admin.begin() as other:
                        _tenant(other, a_id)
                        other.execute(text("UPDATE operations.business_events SET source_type = 'manual_capture'"))

            with app.connect() as connection:
                _tenant(connection, b_id)
                assert connection.execute(
                    text("SELECT business_id FROM operations.business_transaction_counters")
                ).scalars().all() == [b_id]
                connection.rollback()
                _tenant(connection, a_id)
                assert connection.execute(
                    text("SELECT last_value FROM operations.business_transaction_counters")
                ).scalars().all() == [6]
                connection.rollback()

            # Final constraints hold at head.
            with admin.connect() as connection:
                _tenant(connection, a_id)
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text("UPDATE sales.sale_sessions SET transaction_sequence = 1 WHERE id = :id"),
                        {"id": S2},
                    )
                connection.rollback()
                _tenant(connection, a_id)
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text("UPDATE sales.sale_sessions SET void_transaction_sequence = transaction_sequence WHERE id = :id"),
                        {"id": S2},
                    )
                connection.rollback()
                _tenant(connection, a_id)
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text("UPDATE sales.sale_sessions SET transaction_sequence = NULL WHERE id = :id"),
                        {"id": S1},
                    )
                connection.rollback()
                _tenant(connection, a_id)
                with pytest.raises(DBAPIError):
                    connection.execute(
                        text(
                            "UPDATE operations.business_events SET facts = facts - 'transaction_number' "
                            "WHERE event_type = 'sale_confirmed'"
                        )
                    )
                connection.rollback()

            # Downgrade strips enrichment and restores the 0017 shape.
            command.downgrade(cfg, PREVIOUS)
            assert _revision(admin) == PREVIOUS
            with admin.connect() as connection:
                assert connection.execute(
                    text("SELECT to_regclass('operations.business_transaction_counters')")
                ).scalar_one() is None
                columns = connection.execute(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE column_name IN ('transaction_sequence', 'void_transaction_sequence')"
                    )
                ).scalar_one()
                assert columns == 0
                shape = connection.execute(
                    text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'ck_business_events_shape'")
                ).scalar_one()
                assert "transaction_number" not in shape
                assert "close_note" in shape
                facts = _event_facts(connection, a_id, "sale_voided", S2)
                assert "transaction_number" not in facts
                assert "original_transaction_number" not in facts
                assert "transaction_number" not in _event_facts(connection, a_id, "daily_close_completed", snapshot_id)
                assert _event_facts(connection, a_id, "daily_close_completed", snapshot_id)["close_note"] == "todo bien"

            # Re-upgrade reproduces the identical numbering.
            command.upgrade(cfg, "head")
            with admin.connect() as connection:
                assert _sequences(connection, a_id) == sequences
                _tenant(connection, a_id)
                assert connection.execute(
                    text("SELECT last_value FROM operations.business_transaction_counters")
                ).scalar_one() == 6
        finally:
            app.dispose()
            admin.dispose()
