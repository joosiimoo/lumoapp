from __future__ import annotations

from pathlib import Path


def test_compose_has_only_api_and_postgres() -> None:
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text().lower()
    assert "\n  api:" in compose or compose.strip().startswith("services:")
    assert "postgres:" in compose
    assert "api:" in compose
    for forbidden in ("redis", "kafka", "worker:", "vector", "pinecone", "qdrant"):
        assert forbidden not in compose
    raw = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text()
    assert "DATABASE_URL: postgresql+psycopg://lumo_app:" in raw
    assert "DATABASE_ADMIN_URL: postgresql+psycopg://lumo_admin:" in raw
