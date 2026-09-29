from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api.dependencies import get_correlation_id, get_db, get_settings
from app.api.dependencies.auth import resolve_actor_from_authorization
from app.application.workflows.apply_onboarding import ApplyOnboarding
from app.bootstrap.settings import Settings
from app.domain.identity.onboarding import FIELD_BUSINESS_NAME, confirmation_contract, next_required_field
from app.domain.shared.errors import ForbiddenError, ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.audit import SqlAlchemyAuditService
from app.infrastructure.persistence.idempotency import SqlAlchemyIdempotencyService
from app.infrastructure.persistence.repositories import IdentityRepository
from app.infrastructure.persistence.rls import set_current_actor_id, set_current_business_id
router = APIRouter()


class OnboardingApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    currency: str | None = None
    timezone: str | None = None
    payment_methods: list[str] | None = None
    start_using_lumo: bool | None = None


def _principal(request: Request, settings: Settings) -> tuple:
    return resolve_actor_from_authorization(request.headers.get("authorization"), settings)


@router.get("/api/v1/onboarding/status")
def onboarding_status(
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    actor_id, business_id = _principal(request, settings)
    identities = IdentityRepository(session)
    set_current_actor_id(session, actor_id)
    link = identities.find_actor_link(actor_id)
    if link is None:
        if business_id is not None:
            raise ForbiddenError("pre-tenant status required")
        return {
            "onboarding_status": "not_started",
            "next_required_field": FIELD_BUSINESS_NAME,
        }
    set_current_business_id(session, link.business_id)
    business = identities.get_business(TenantContext(business_id=link.business_id, actor_id=actor_id))
    methods = list(business.enabled_payment_methods) if business.enabled_payment_methods is not None else None
    nxt = next_required_field(
        has_business=True,
        currency=business.currency,
        timezone=business.timezone,
        enabled_payment_methods=methods,
        onboarding_status=business.onboarding_status,
    )
    ui: list[dict[str, Any]] = []
    if nxt == "ready_to_complete" and methods and business.currency and business.timezone:
        ui = [
            confirmation_contract(
                name=business.name,
                currency=business.currency,
                timezone=business.timezone,
                enabled_payment_methods=methods,
            )
        ]
    return {
        "onboarding_status": business.onboarding_status,
        "next_required_field": nxt,
        "ui": ui,
        "business": {
            "id": str(business.id),
            "name": business.name,
            "currency": business.currency,
            "timezone": business.timezone,
            "enabled_payment_methods": methods,
        },
    }


@router.post("/api/v1/onboarding/apply")
def apply_onboarding(
    payload: OnboardingApplyRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    correlation_id: str = Depends(get_correlation_id),
) -> dict[str, Any]:
    if not idempotency_key:
        raise ValidationAppError("Idempotency-Key is required")
    actor_id, business_id = _principal(request, settings)
    workflow = ApplyOnboarding(
        IdentityRepository(session),
        SqlAlchemyAuditService(session),
        SqlAlchemyIdempotencyService(session),
        token_secret=settings.dev_token_secret,
    )
    body = payload.model_dump(exclude_none=True)
    return workflow.execute(
        actor_id=actor_id,
        business_id=business_id,
        payload=body,
        idempotency_key=idempotency_key,
        correlation_id=correlation_id,
    )
