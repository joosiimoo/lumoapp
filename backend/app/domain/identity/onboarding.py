"""Deterministic onboarding state. No framework imports."""

from __future__ import annotations

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
PERSISTED_STATUSES = frozenset({STATUS_IN_PROGRESS, STATUS_COMPLETED})

FIELD_BUSINESS_NAME = "business_name"
FIELD_CURRENCY = "currency"
FIELD_TIMEZONE = "timezone"
FIELD_PAYMENT_METHODS = "payment_methods"
FIELD_READY = "ready_to_complete"

SUPPORTED_CURRENCIES = frozenset({"MXN"})
SUPPORTED_TIMEZONES = frozenset(
    {
        "America/Mexico_City",
        "America/Cancun",
        "America/Tijuana",
        "America/Hermosillo",
        "America/Mazatlan",
        "America/Chihuahua",
        "America/Merida",
        "America/Monterrey",
        "America/Bahia_Banderas",
    }
)
PAYMENT_METHODS = ("cash", "card", "transfer")
PAYMENT_METHOD_SET = frozenset(PAYMENT_METHODS)
MAX_BUSINESS_NAME_LENGTH = 200

PRE_TENANT_OPERATION = "onboarding.apply"
TENANT_OPERATION = "onboarding.apply"


class OnboardingValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def normalize_business_name(raw: str) -> str:
    collapsed = " ".join(raw.split())
    if not collapsed:
        raise OnboardingValidationError("EMPTY_BUSINESS_NAME", "business name is empty")
    if len(collapsed) > MAX_BUSINESS_NAME_LENGTH:
        raise OnboardingValidationError("BUSINESS_NAME_TOO_LONG", "business name is too long")
    return collapsed


def validate_currency(raw: str) -> str:
    code = raw.strip().upper()
    if code not in SUPPORTED_CURRENCIES:
        raise OnboardingValidationError("UNSUPPORTED_CURRENCY", "currency is not supported")
    return code


def validate_timezone(raw: str) -> str:
    zone = raw.strip()
    if zone not in SUPPORTED_TIMEZONES:
        raise OnboardingValidationError("UNSUPPORTED_TIMEZONE", "timezone is not supported")
    return zone


def validate_payment_methods(raw: list[str]) -> list[str]:
    if not raw:
        raise OnboardingValidationError("EMPTY_PAYMENT_METHODS", "at least one payment method is required")
    unknown = [item for item in raw if item not in PAYMENT_METHOD_SET]
    if unknown:
        raise OnboardingValidationError("UNKNOWN_PAYMENT_METHOD", "payment method is not supported")
    ordered = [method for method in PAYMENT_METHODS if method in set(raw)]
    if not ordered:
        raise OnboardingValidationError("EMPTY_PAYMENT_METHODS", "at least one payment method is required")
    return ordered


def next_required_field(
    *,
    has_business: bool,
    currency: str | None,
    timezone: str | None,
    enabled_payment_methods: list[str] | None,
    onboarding_status: str | None,
) -> str | None:
    if not has_business:
        return FIELD_BUSINESS_NAME
    if onboarding_status == STATUS_COMPLETED:
        return None
    if currency is None:
        return FIELD_CURRENCY
    if timezone is None:
        return FIELD_TIMEZONE
    if enabled_payment_methods is None or len(enabled_payment_methods) == 0:
        return FIELD_PAYMENT_METHODS
    return FIELD_READY


def sales_allowed(*, onboarding_status: str) -> bool:
    return onboarding_status == STATUS_COMPLETED


def confirmation_contract(
    *,
    name: str,
    currency: str,
    timezone: str,
    enabled_payment_methods: list[str],
) -> dict:
    methods = list(enabled_payment_methods)
    return {
        "component": "onboarding_confirmation",
        "version": 1,
        "data": {
            "name": name,
            "currency": currency,
            "timezone": timezone,
            "enabled_payment_methods": methods,
        },
        "actions": [
            {
                "action_id": "start_using_lumo",
                "option_id": None,
                "context_token": "ready_to_complete",
                "idempotency_key": "start_using_lumo",
            }
        ],
        "fallback_text": f"{name} · {currency} · {timezone} · {', '.join(methods)}",
    }


def payment_method_allowed(*, enabled_payment_methods: list[str] | None, method: str) -> bool:
    if enabled_payment_methods is None:
        return method in PAYMENT_METHOD_SET
    return method in enabled_payment_methods
