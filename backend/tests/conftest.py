from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies.auth import issue_dev_token
from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from app.domain.shared.ids import new_uuid7
from app.infrastructure.persistence.engine import create_engine_from_settings, create_session_factory
from app.infrastructure.persistence.models import BusinessRow, MembershipRow, UserRow
from app.infrastructure.persistence.rls import set_current_business_id

TEST_SECRET = "test-dev-secret-16-chars-minimum"
DEFAULT_APP_URL = "postgresql+psycopg://lumo_app:lumo_app@localhost:5433/lumo"
DEFAULT_ADMIN_URL = "postgresql+psycopg://lumo_admin:lumo_admin@localhost:5433/lumo"


def settings_kwargs(**overrides: str) -> dict[str, str]:
    values = {
        "APP_ENV": "test",
        "DATABASE_URL": os.environ.get("DATABASE_URL", DEFAULT_APP_URL),
        "DATABASE_ADMIN_URL": os.environ.get("DATABASE_ADMIN_URL", DEFAULT_ADMIN_URL),
        "DEV_TOKEN_SECRET": TEST_SECRET,
    }
    values.update(overrides)
    return values


def make_settings() -> Settings:
    return Settings.model_validate(settings_kwargs())


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def postgres_available(settings: Settings) -> bool:
    try:
        engine = create_engine_from_settings(settings)
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture
def db_session(settings: Settings) -> Iterator[Session]:
    if not postgres_available(settings):
        pytest.skip("PostgreSQL is not available")
    engine = create_engine_from_settings(settings)
    factory = create_session_factory(engine)
    session = factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
        engine.dispose()


def seed_business(session: Session, *, name: str) -> tuple[UUID, UUID, str]:
    business_id = new_uuid7()
    user_id = new_uuid7()
    set_current_business_id(session, business_id)
    session.add(
        BusinessRow(
            id=business_id,
            name=name,
            currency="MXN",
            timezone="America/Mexico_City",
            locale="es-MX",
        )
    )
    session.flush()
    session.add(UserRow(id=user_id, business_id=business_id, name=f"{name} owner"))
    session.flush()
    session.add(MembershipRow(business_id=business_id, user_id=user_id, role="owner"))
    session.commit()
    token = issue_dev_token(user_id=user_id, business_id=business_id, secret=TEST_SECRET)
    return business_id, user_id, token
