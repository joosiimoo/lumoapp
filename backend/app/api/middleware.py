from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.domain.shared.ids import new_uuid7


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        correlation_id = request.headers.get("x-correlation-id") or str(new_uuid7())
        request_id = str(uuid4())
        request.state.correlation_id = correlation_id
        request.state.request_id = request_id
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            _log_request(request, started, 500)
            raise
        response.headers["X-Correlation-ID"] = correlation_id
        _log_request(request, started, response.status_code)
        return response


def _log_request(request: Request, started: float, status_code: int) -> None:
    import logging

    duration_ms = int((perf_counter() - started) * 1000)
    logger = logging.getLogger("lumo.http")
    extra = {
        "service": "lumo-api",
        "environment": getattr(request.app.state, "app_env", None),
        "correlation_id": getattr(request.state, "correlation_id", None),
        "request_id": getattr(request.state, "request_id", None),
        "route": request.url.path,
        "duration_ms": duration_ms,
        "outcome": str(status_code),
    }
    logger.info("request", extra=extra)
