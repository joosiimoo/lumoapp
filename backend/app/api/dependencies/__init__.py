from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies.auth import resolve_tenant_from_authorization
from app.bootstrap.settings import Settings
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.rls import set_current_business_id


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Generator[Session, None, None]:
    session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_tenant(
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> TenantContext:
    _ = request.headers.get("x-business-id")
    tenant = resolve_tenant_from_authorization(request.headers.get("authorization"), settings)
    set_current_business_id(session, tenant.business_id)
    return tenant


def get_correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")
