from datetime import UTC, datetime

import pytest

from app.domain.operations import InvalidBusinessTimezone, business_date_for


def test_mexico_city_midnight_boundary() -> None:
    before = datetime(2026, 9, 22, 5, 59, 59, tzinfo=UTC)
    after = datetime(2026, 9, 22, 6, 0, 0, tzinfo=UTC)
    assert business_date_for(before, "America/Mexico_City") == datetime(2026, 9, 21).date()
    assert business_date_for(after, "America/Mexico_City") == datetime(2026, 9, 22).date()


def test_unknown_timezone_fails() -> None:
    instant = datetime(2026, 9, 21, 18, 0, tzinfo=UTC)
    with pytest.raises(InvalidBusinessTimezone):
        business_date_for(instant, "Not/AZone")


def test_naive_instant_rejected() -> None:
    with pytest.raises(ValueError):
        business_date_for(datetime(2026, 9, 21, 18, 0), "America/Mexico_City")
