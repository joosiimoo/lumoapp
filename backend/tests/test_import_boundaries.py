from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DOMAIN = {"fastapi", "sqlalchemy", "alembic", "openai", "anthropic"}
FORBIDDEN_AGENT_APP = {"sqlalchemy.orm", "app.infrastructure.persistence.engine", "app.infrastructure.persistence.models"}


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
            names.add(node.module)
    return names


def test_domain_does_not_import_frameworks() -> None:
    domain = BACKEND_ROOT / "app" / "domain"
    for path in domain.rglob("*.py"):
        imported = _imported_modules(path)
        overlap = imported & FORBIDDEN_DOMAIN
        assert not overlap, f"{path} imports forbidden modules: {overlap}"


def test_agent_and_application_do_not_import_orm() -> None:
    for folder in ("agent", "application"):
        root = BACKEND_ROOT / "app" / folder
        for path in root.rglob("*.py"):
            source = path.read_text()
            assert "sqlalchemy.orm" not in source
            assert "create_session_factory" not in source
            assert "from app.infrastructure.persistence.models" not in source
