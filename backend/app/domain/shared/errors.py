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
