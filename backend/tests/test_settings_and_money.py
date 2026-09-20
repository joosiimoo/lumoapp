from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.bootstrap.settings import Settings, clear_settings_cache
from app.domain.shared.money import Money
from decimal import Decimal


def _urls() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+psycopg://lumo_app:lumo_app@localhost/lumo",
        "DATABASE_ADMIN_URL": "postgresql+psycopg://lumo_admin:lumo_admin@localhost/lumo",
    }


def test_missing_database_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_ADMIN_URL", raising=False)
    clear_settings_cache()
    with pytest.raises(ValidationError):
        Settings.model_validate({"APP_ENV": "local", "DEV_TOKEN_SECRET": "test-dev-secret-16"})


def test_missing_database_admin_url_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_ADMIN_URL", raising=False)
    clear_settings_cache()
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "APP_ENV": "local",
                "DATABASE_URL": "postgresql+psycopg://lumo_app:lumo_app@localhost/lumo",
                "DEV_TOKEN_SECRET": "test-dev-secret-16",
            }
        )


def test_unknown_app_env_fails() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "APP_ENV": "qa",
                **_urls(),
                "DEV_TOKEN_SECRET": "test-dev-secret-16",
            }
        )


def test_known_app_envs_are_accepted() -> None:
    for env in ("local", "test", "staging", "production"):
        settings = Settings.model_validate(
            {
                "APP_ENV": env,
                **_urls(),
                "DEV_TOKEN_SECRET": "test-dev-secret-16",
            }
        )
        assert settings.app_env.value == env
        assert "lumo_app" in settings.sqlalchemy_url
        assert "lumo_admin" in settings.sqlalchemy_admin_url


def test_money_rejects_float() -> None:
    with pytest.raises(TypeError, match="float"):
        Money(1.23, "MXN")  # type: ignore[arg-type]


def test_money_accepts_decimal() -> None:
    money = Money(Decimal("10.50"), "mxn")
    assert money.to_json() == {"amount": "10.50", "currency": "MXN"}
