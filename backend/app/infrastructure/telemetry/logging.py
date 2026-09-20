from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "severity": record.levelname.lower(),
            "service": getattr(record, "service", "lumo-api"),
            "environment": getattr(record, "environment", None),
            "correlation_id": getattr(record, "correlation_id", None),
            "request_id": getattr(record, "request_id", None),
            "route": getattr(record, "route", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "outcome": getattr(record, "outcome", None),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["error_code"] = getattr(record, "error_code", "INTERNAL_ERROR")
        return json.dumps({k: v for k, v in payload.items() if v is not None})


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").disabled = True
