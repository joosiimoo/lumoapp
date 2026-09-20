from __future__ import annotations

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


def _as_sqlalchemy_url(value: str) -> str:
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="forbid")

    app_env: AppEnv = Field(alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL", min_length=1)
    database_admin_url: str = Field(alias="DATABASE_ADMIN_URL", min_length=1)
    dev_token_secret: str = Field(alias="DEV_TOKEN_SECRET", min_length=16)
    service_name: str = Field(default="lumo-api", alias="SERVICE_NAME")

    @field_validator("database_url", "database_admin_url")
    @classmethod
    def database_url_must_be_postgres(cls, value: str) -> str:
        if not value.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("database URL must be a PostgreSQL URL")
        return value

    @property
    def sqlalchemy_url(self) -> str:
        return _as_sqlalchemy_url(self.database_url)

    @property
    def sqlalchemy_admin_url(self) -> str:
        return _as_sqlalchemy_url(self.database_admin_url)

    @property
    def allows_dev_tokens(self) -> bool:
        return self.app_env in {AppEnv.LOCAL, AppEnv.TEST}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def clear_settings_cache() -> None:
    get_settings.cache_clear()
