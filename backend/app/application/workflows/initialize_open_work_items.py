from __future__ import annotations

from datetime import datetime

from app.infrastructure.persistence.work_item_bootstrap import bootstrap_open_today_work_items


def initialize_open_today_work_items(*, admin_url: str, now: datetime | None = None) -> int:
    """Deploy command: initialize WorkItems for open OperationalDays dated today."""
    return bootstrap_open_today_work_items(admin_url=admin_url, now=now)
