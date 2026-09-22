from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InvalidBusinessTimezone(ValueError):
    """The business IANA timezone cannot be used to compute a business date."""


def business_date_for(confirmed_at: datetime, timezone_name: str) -> date:
    """Local calendar date of a UTC instant in the business IANA timezone.

    Runtime membership uses ``confirmed_at``. ``updated_at`` is not an input.
    """
    if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
        raise ValueError("confirmed_at must be timezone-aware UTC")
    if confirmed_at.utcoffset() != timedelta(0):
        raise ValueError("confirmed_at must be timezone-aware UTC")
    if not timezone_name or not timezone_name.strip():
        raise InvalidBusinessTimezone("business timezone is missing")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise InvalidBusinessTimezone(timezone_name) from exc
    instant = confirmed_at.astimezone(UTC)
    return instant.astimezone(zone).date()
