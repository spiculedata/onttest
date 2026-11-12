"""The as-of moment and the idle window, shared by the checks and Priya's screen.

As of 31 Oct 2026, end of day, AEST (fixed UTC+10, as the rules say). The idle window is the
14 days ending then: 18 Oct 00:00 to 31 Oct 23:59:59 AEST.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

AEST = timezone(timedelta(hours=10), "AEST")
IDLE_WINDOW_DAYS = 14


def idle_window(as_of: date) -> tuple[datetime, datetime]:
    end = datetime.combine(as_of, time(23, 59, 59), tzinfo=AEST)
    start = datetime.combine(as_of - timedelta(days=IDLE_WINDOW_DAYS - 1), time(0, 0), tzinfo=AEST)
    return start, end
