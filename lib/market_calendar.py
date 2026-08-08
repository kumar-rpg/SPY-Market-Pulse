"""US market trading-day / session-window gating.

Cloud routine cron fires on a static UTC schedule that can't track DST, so
every entrypoint script re-derives the real US/Eastern time itself and no-ops
cleanly if it's not actually a trading day or the intended window. This is
what keeps the DST-imprecise cron design (see plan) safe.

NYSE full-day closures. Early closes (day after Thanksgiving, Dec 24 some
years) are NOT modeled — accepted gap for this test run.
"""

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

NYSE_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Washington's Birthday
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),   # Independence Day (observed, Jul 4 falls on a Saturday)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 12, 25), # Christmas
}

PREOPEN_START = time(9, 15)
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


def now_et():
    return datetime.now(ET)


def is_trading_day(d):
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS_2026


def session_phase(dt=None):
    """Returns 'preopen' (9:15-9:30), 'session' (9:30-16:00), or 'closed'."""
    dt = dt or now_et()
    if not is_trading_day(dt.date()):
        return "closed"
    t = dt.time()
    if PREOPEN_START <= t < SESSION_OPEN:
        return "preopen"
    if SESSION_OPEN <= t < SESSION_CLOSE:
        return "session"
    return "closed"
