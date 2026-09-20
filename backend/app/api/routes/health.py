from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.domain.shared.errors import DependencyUnavailableError
from app.infrastructure.persistence.engine import ping_database

router = APIRouter()


@router.get("/health")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(request: Request) -> JSONResponse:
    try:
        ping_database(request.app.state.engine)
    except SQLAlchemyError as exc:
        raise DependencyUnavailableError("database is not ready") from exc
    return JSONResponse({"status": "ok", "database": True})
