from __future__ import annotations

import json
from hashlib import sha256
from typing import Any
from uuid import UUID

from app.api.dependencies.auth import issue_dev_token
from app.application.ports import AuditService, IdempotencyService
from app.domain.identity.onboarding import (
    PRE_TENANT_OPERATION,
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    TENANT_OPERATION,
    OnboardingValidationError,
    confirmation_contract,
    next_required_field,
    normalize_business_name,
    validate_currency,
    validate_payment_methods,
    validate_timezone,
)
from app.domain.shared.errors import ValidationAppError
from app.domain.shared.tenant import TenantContext
from app.infrastructure.persistence.repositories import IdentityRepository
from app.infrastructure.persistence.rls import set_current_actor_id, set_current_business_id


def map_onboarding_slots(slots: dict[str, Any]) -> dict[str, Any]:
    """Copy only registered onboarding writes. Ignore every other field."""
    allowed = ("name", "currency", "timezone", "payment_methods", "start_using_lumo")
    mapped: dict[str, Any] = {}
    for key in allowed:
        if key in slots:
            mapped[key] = slots[key]
    return mapped


class ApplyOnboarding:
    def __init__(
        self,
        identities: IdentityRepository,
        audit: AuditService,
        idempotency: IdempotencyService,
        *,
        token_secret: str,
    ) -> None:
        self._identities = identities
        self._session = identities._session
        self._audit = audit
        self._idempotency = idempotency
        self._token_secret = token_secret

    def execute(
        self,
        *,
        actor_id: UUID,
        business_id: UUID | None,
        payload: dict[str, Any],
        idempotency_key: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        if "business_id" in payload:
            raise ValidationAppError("client must not select business_id")
        fields = map_onboarding_slots(payload)
        request_hash = sha256(
            json.dumps(fields, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        set_current_actor_id(self._session, actor_id)
        link = self._identities.find_actor_link(actor_id)
        if link is None:
            return self._bootstrap(
                actor_id=actor_id,
                fields=fields,
                idempotency_key=idempotency_key,
                correlation_id=correlation_id,
                request_hash=request_hash,
            )
        if business_id is not None and business_id != link.business_id:
            raise ValidationAppError("token tenant does not match actor link")
        return self._apply_existing(
            actor_id=actor_id,
            business_id=link.business_id,
            fields=fields,
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_hash=request_hash,
        )

    def _bootstrap(
        self,
        *,
        actor_id: UUID,
        fields: dict[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_hash: str,
    ) -> dict[str, Any]:
        if "name" not in fields:
            raise ValidationAppError("business name is required")
        try:
            name = normalize_business_name(str(fields["name"]))
        except OnboardingValidationError as exc:
            raise ValidationAppError(exc.message) from exc
        scope = TenantContext(business_id=actor_id, actor_id=actor_id)
        set_current_business_id(self._session, actor_id)
        replay = self._idempotency.begin(
            tenant=scope,
            operation_type=PRE_TENANT_OPERATION,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay["body"]
        business = self._identities.bootstrap_owner_business(actor_id=actor_id, name=name)
        tenant = TenantContext(business_id=business.id, actor_id=actor_id)
        self._audit.record(
            tenant=tenant,
            action="business.created",
            route_or_tool="onboarding.apply@1",
            result="ok",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            after_payload={"name": name, "onboarding_status": STATUS_IN_PROGRESS},
        )
        self._apply_fields(
            business=business,
            tenant=tenant,
            fields=fields,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            skip_name=True,
        )
        body = self._body(business, actor_id)
        set_current_business_id(self._session, actor_id)
        self._idempotency.complete(
            tenant=scope,
            operation_type=PRE_TENANT_OPERATION,
            key=idempotency_key,
            status_code=200,
            body=body,
        )
        return body

    def _apply_existing(
        self,
        *,
        actor_id: UUID,
        business_id: UUID,
        fields: dict[str, Any],
        idempotency_key: str,
        correlation_id: str,
        request_hash: str,
    ) -> dict[str, Any]:
        tenant = TenantContext(business_id=business_id, actor_id=actor_id)
        set_current_business_id(self._session, business_id)
        replay = self._idempotency.begin(
            tenant=tenant,
            operation_type=TENANT_OPERATION,
            key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return replay["body"]
        business = self._identities.get_business(tenant)
        if business.onboarding_status == STATUS_COMPLETED and _has_config_edit(fields):
            raise ValidationAppError("onboarding configuration is closed")
        self._apply_fields(
            business=business,
            tenant=tenant,
            fields=fields,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            skip_name=False,
        )
        body = self._body(business, actor_id)
        self._idempotency.complete(
            tenant=tenant,
            operation_type=TENANT_OPERATION,
            key=idempotency_key,
            status_code=200,
            body=body,
        )
        return body

    def _apply_fields(
        self,
        *,
        business,
        tenant: TenantContext,
        fields: dict[str, Any],
        correlation_id: str,
        idempotency_key: str,
        skip_name: bool,
    ) -> None:
        if business.onboarding_status == STATUS_COMPLETED:
            return
        if not skip_name and "name" in fields:
            try:
                business.name = normalize_business_name(str(fields["name"]))
            except OnboardingValidationError as exc:
                raise ValidationAppError(exc.message) from exc
        if "currency" in fields:
            try:
                currency = validate_currency(str(fields["currency"]))
            except OnboardingValidationError as exc:
                raise ValidationAppError(exc.message) from exc
            if business.currency != currency:
                business.currency = currency
                self._audit.record(
                    tenant=tenant,
                    action="business.currency_configured",
                    route_or_tool="onboarding.apply@1",
                    result="ok",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    after_payload={"currency": currency},
                )
        if "timezone" in fields:
            try:
                timezone = validate_timezone(str(fields["timezone"]))
            except OnboardingValidationError as exc:
                raise ValidationAppError(exc.message) from exc
            if business.timezone != timezone:
                business.timezone = timezone
                self._audit.record(
                    tenant=tenant,
                    action="business.timezone_configured",
                    route_or_tool="onboarding.apply@1",
                    result="ok",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    after_payload={"timezone": timezone},
                )
        if "payment_methods" in fields:
            try:
                methods = validate_payment_methods(list(fields["payment_methods"]))
            except OnboardingValidationError as exc:
                raise ValidationAppError(exc.message) from exc
            if list(business.enabled_payment_methods or []) != methods:
                business.enabled_payment_methods = methods
                self._audit.record(
                    tenant=tenant,
                    action="business.payment_methods_configured",
                    route_or_tool="onboarding.apply@1",
                    result="ok",
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    after_payload={"enabled_payment_methods": methods},
                )
        if fields.get("start_using_lumo") is True:
            nxt = next_required_field(
                has_business=True,
                currency=business.currency,
                timezone=business.timezone,
                enabled_payment_methods=list(business.enabled_payment_methods)
                if business.enabled_payment_methods is not None
                else None,
                onboarding_status=business.onboarding_status,
            )
            if nxt != "ready_to_complete":
                raise ValidationAppError("onboarding is not ready to complete")
            business.onboarding_status = STATUS_COMPLETED
            self._audit.record(
                tenant=tenant,
                action="business.onboarding_completed",
                route_or_tool="onboarding.apply@1",
                result="ok",
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                after_payload={"onboarding_status": STATUS_COMPLETED},
            )
        self._session.flush()

    def _body(self, business, actor_id: UUID) -> dict[str, Any]:
        methods = (
            list(business.enabled_payment_methods) if business.enabled_payment_methods is not None else None
        )
        nxt = next_required_field(
            has_business=True,
            currency=business.currency,
            timezone=business.timezone,
            enabled_payment_methods=methods,
            onboarding_status=business.onboarding_status,
        )
        token = issue_dev_token(
            user_id=actor_id,
            business_id=business.id,
            secret=self._token_secret,
        )
        summary = None
        ui: list[dict[str, Any]] = []
        if nxt == "ready_to_complete" and methods:
            summary = {
                "name": business.name,
                "currency": business.currency,
                "timezone": business.timezone,
                "enabled_payment_methods": methods,
            }
            ui = [
                confirmation_contract(
                    name=business.name,
                    currency=business.currency,
                    timezone=business.timezone,
                    enabled_payment_methods=methods,
                )
            ]
        return {
            "business_id": str(business.id),
            "onboarding_status": business.onboarding_status,
            "next_required_field": nxt,
            "name": business.name,
            "currency": business.currency,
            "timezone": business.timezone,
            "enabled_payment_methods": methods,
            "confirmation": summary,
            "ui": ui,
            "access_token": token,
        }


def _has_config_edit(fields: dict[str, Any]) -> bool:
    return any(key in fields for key in ("name", "currency", "timezone", "payment_methods"))
