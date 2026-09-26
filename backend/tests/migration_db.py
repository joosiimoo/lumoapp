"""Schema-downgrade tests run here. They must not open the application database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from app.bootstrap.settings import get_settings

MIGRATION_DB_NAME = "lumo_migration_test"
_MAINTENANCE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"
_MIGRATION_MAINTENANCE_URL = f"postgresql+psycopg://postgres:postgres@localhost:5432/{MIGRATION_DB_NAME}"
_ADMIN_URL = f"postgresql+psycopg://lumo_admin:lumo_admin@localhost:5432/{MIGRATION_DB_NAME}"
_APP_URL = f"postgresql+psycopg://lumo_app:lumo_app@localhost:5432/{MIGRATION_DB_NAME}"


def ensure_migration_database() -> None:
    engine = create_engine(_MAINTENANCE_URL, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": MIGRATION_DB_NAME},
            ).scalar()
            if exists is None:
                connection.execute(text(f"CREATE DATABASE {MIGRATION_DB_NAME} OWNER lumo_admin"))
            connection.execute(text(f"GRANT CONNECT ON DATABASE {MIGRATION_DB_NAME} TO lumo_admin, lumo_app"))
        admin = create_engine(_MIGRATION_MAINTENANCE_URL, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                connection.execute(text("ALTER SCHEMA public OWNER TO lumo_admin"))
                connection.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO lumo_admin"))
        finally:
            admin.dispose()
    finally:
        engine.dispose()


@contextmanager
def use_migration_database() -> Iterator[None]:
    """Point Alembic and test engines at the schema database for one test."""
    ensure_migration_database()
    keys = ("DATABASE_URL", "DATABASE_ADMIN_URL")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["DATABASE_URL"] = _APP_URL
    os.environ["DATABASE_ADMIN_URL"] = _ADMIN_URL
    get_settings.cache_clear()
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
