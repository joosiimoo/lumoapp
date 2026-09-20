from __future__ import annotations

from fastapi.testclient import TestClient

from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from tests.conftest import settings_kwargs


def _client() -> TestClient:
    return TestClient(create_app(Settings.model_validate(settings_kwargs())), raise_server_exceptions=False)


def test_liveness() -> None:
    response = _client().get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert "X-Correlation-ID" in response.headers


def test_correlation_id_is_echoed() -> None:
    response = _client().get("/health", headers={"X-Correlation-ID": "abc"})
    assert response.headers["X-Correlation-ID"] == "abc"


def test_invalid_json_uses_error_envelope() -> None:
    response = _client().post(
        "/api/v1/_test/echo",
        content="{not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "VALIDATION_ERROR"
    assert body["correlation_id"]
    assert "traceback" not in str(response.json()).lower()


def test_unhandled_error_hides_stack() -> None:
    response = _client().get("/api/v1/_test/fail")
    assert response.status_code == 500
    body = response.json()["error"]
    assert body["code"] == "INTERNAL_ERROR"
    assert "intentional failure" not in body["message"]
    assert "traceback" not in str(response.json()).lower()
    assert "RuntimeError" not in str(response.json())
