from __future__ import annotations

import json
from pathlib import Path

from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings


def main() -> None:
    settings = Settings.model_validate(
        {
            "APP_ENV": "local",
            "DATABASE_URL": "postgresql+psycopg://lumo_app:lumo_app@localhost:5433/lumo",
            "DATABASE_ADMIN_URL": "postgresql+psycopg://lumo_admin:lumo_admin@localhost:5433/lumo",
            "DEV_TOKEN_SECRET": "local-dev-secret-do-not-use-in-prod",
        }
    )
    app = create_app(settings)
    schema = app.openapi()
    out = Path(__file__).resolve().parents[1] / "openapi.json"
    out.write_text(json.dumps(schema, indent=2))
    print(out)


if __name__ == "__main__":
    main()
