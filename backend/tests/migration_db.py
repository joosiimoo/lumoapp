"""Schema-downgrade tests run here. They must not open the application database."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from app.bootstrap.settings import get_settings

MIGRATION_DB_NAME = "lumo_migration_test"
CLEAN_PROOF_DB_NAME = "lumo_clean_0016"
_MAINTENANCE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres"


def _db_urls(name: str) -> tuple[str, str, str]:
    maintenance = f"postgresql+psycopg://postgres:postgres@localhost:5432/{name}"
    admin = f"postgresql+psycopg://lumo_admin:lumo_admin@localhost:5432/{name}"
    app = f"postgresql+psycopg://lumo_app:lumo_app@localhost:5432/{name}"
    return maintenance, admin, app


_MIGRATION_MAINTENANCE_URL, _ADMIN_URL, _APP_URL = _db_urls(MIGRATION_DB_NAME)


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


def recreate_database(name: str) -> tuple[str, str]:
    """Drop and recreate a disposable Postgres database owned by lumo_admin.

    Returns (app_url, admin_url) for the fresh database.
    """
    if name in {"postgres", "template0", "template1", "lumo"}:
        raise ValueError(f"refusing to recreate protected database {name}")
    maintenance, admin_url, app_url = _db_urls(name)
    engine = create_engine(_MAINTENANCE_URL, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            connection.execute(
                text(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = :name AND pid <> pg_backend_pid()
                    """
                ),
                {"name": name},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {name}"))
            connection.execute(text(f"CREATE DATABASE {name} OWNER lumo_admin"))
            connection.execute(text(f"GRANT CONNECT ON DATABASE {name} TO lumo_admin, lumo_app"))
            connection.execute(text(f"GRANT CREATE ON DATABASE {name} TO lumo_admin"))
        admin = create_engine(maintenance, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                connection.execute(text("ALTER SCHEMA public OWNER TO lumo_admin"))
                connection.execute(text("GRANT USAGE, CREATE ON SCHEMA public TO lumo_admin"))
                connection.execute(text("REVOKE ALL ON SCHEMA public FROM PUBLIC"))
                connection.execute(text("REVOKE ALL ON SCHEMA public FROM lumo_app"))
        finally:
            admin.dispose()
    finally:
        engine.dispose()
    return app_url, admin_url


@contextmanager
def use_database_urls(app_url: str, admin_url: str) -> Iterator[None]:
    keys = ("DATABASE_URL", "DATABASE_ADMIN_URL")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["DATABASE_URL"] = app_url
    os.environ["DATABASE_ADMIN_URL"] = admin_url
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


@contextmanager
def use_migration_database() -> Iterator[None]:
    """Point Alembic and test engines at the schema database for one test."""
    ensure_migration_database()
    with use_database_urls(_APP_URL, _ADMIN_URL):
        yield


@contextmanager
def use_clean_proof_database() -> Iterator[None]:
    """Disposable empty database for base→head migration proof."""
    app_url, admin_url = recreate_database(CLEAN_PROOF_DB_NAME)
    with use_database_urls(app_url, admin_url):
        yield
