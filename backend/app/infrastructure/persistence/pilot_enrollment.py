from __future__ import annotations

from datetime import date


def enrollment_range_overlaps_window(
    *,
    pilot_started_on: date,
    pilot_ended_on: date | None,
    window_start: date,
    window_end: date,
) -> bool:
    range_end = pilot_ended_on if pilot_ended_on is not None else date.max
    return pilot_started_on <= window_end and window_start <= range_end
