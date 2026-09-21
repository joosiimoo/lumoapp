from __future__ import annotations

from typing import Any


class AppError(Exception):
    code = "INTERNAL_ERROR"
    http_status = 500
    retryable = True

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationAppError(AppError):
    code = "VALIDATION_ERROR"
    http_status = 422
    retryable = False


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    http_status = 403
    retryable = False


class TenantScopeViolationError(AppError):
    code = "TENANT_SCOPE_VIOLATION"
    http_status = 404
    retryable = False


class IdempotencyConflictError(AppError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409
    retryable = False


class DependencyUnavailableError(AppError):
    code = "DEPENDENCY_UNAVAILABLE"
    http_status = 503
    retryable = True


class InternalError(AppError):
    code = "INTERNAL_ERROR"
    http_status = 500
    retryable = True


class AmbiguousProductError(AppError):
    code = "AMBIGUOUS_PRODUCT"
    http_status = 409
    retryable = False


class ProductNotFoundError(AppError):
    code = "PRODUCT_NOT_FOUND"
    http_status = 404
    retryable = False


class UnitNotSupportedError(AppError):
    code = "UNIT_NOT_SUPPORTED"
    http_status = 422
    retryable = False


class SaleNotOpenError(AppError):
    code = "SALE_NOT_OPEN"
    http_status = 409
    retryable = False


class SaleEmptyError(AppError):
    code = "SALE_EMPTY"
    http_status = 409
    retryable = False


class SaleNotReadyToChargeError(AppError):
    code = "SALE_NOT_READY_TO_CHARGE"
    http_status = 409
    retryable = False


class SaleNotFoundError(AppError):
    code = "SALE_NOT_FOUND"
    http_status = 404
    retryable = False


class PaymentMethodUnknownError(AppError):
    code = "PAYMENT_METHOD_UNKNOWN"
    http_status = 422
    retryable = False
