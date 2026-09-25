from __future__ import annotations

from app.application.workflows.initialize_open_work_items import initialize_open_today_work_items
from app.bootstrap.settings import get_settings


def main() -> None:
    inserted = initialize_open_today_work_items(admin_url=get_settings().sqlalchemy_admin_url)
    print(f"initialized {inserted} work items")


if __name__ == "__main__":
    main()
