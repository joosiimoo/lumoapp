from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.domain.shared.errors import AppError, InternalError


def error_body(
    *,
    code: str,
    message: str,
    correlation_id: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "retryable": retryable,
            "correlation_id": correlation_id,
        }
    }


def correlation_id_of(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content=error_body(
            code=exc.code,
            message=exc.message,
            correlation_id=correlation_id_of(request),
            details=exc.details,
            retryable=exc.retryable,
        ),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_body(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            correlation_id=correlation_id_of(request),
            details={"errors": exc.errors()},
            retryable=False,
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = "FORBIDDEN" if exc.status_code == 403 else "INTERNAL_ERROR"
    if exc.status_code == 404:
        code = "TENANT_SCOPE_VIOLATION"
    if exc.status_code == 422:
        code = "VALIDATION_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(
            code=code,
            message=str(exc.detail),
            correlation_id=correlation_id_of(request),
            retryable=exc.status_code >= 500,
        ),
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    _ = InternalError(str(exc))
    return JSONResponse(
        status_code=500,
        content=error_body(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred",
            correlation_id=correlation_id_of(request),
            retryable=True,
        ),
    )
