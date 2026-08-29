"""Exchange sessions.

"The next session" is not "tomorrow". It steps over weekends, market holidays,
and the early closes around Thanksgiving and Christmas Eve. Hand-rolling that
produces silent off-by-one-day errors in a backtest which are close to
impossible to spot in aggregate results, so it is delegated to a maintained
calendar (research.md R6).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache

import exchange_calendars as xcals
import pandas as pd


@lru_cache(maxsize=4)
def _calendar(name: str) -> xcals.ExchangeCalendar:
    return xcals.get_calendar(name)


class ExchangeSessions:
    """Session boundaries for one exchange, in UTC."""

    def __init__(self, name: str = "XNYS") -> None:
        self.name = name
        self._cal = _calendar(name)

    def is_session(self, day: date) -> bool:
        return bool(self._cal.is_session(pd.Timestamp(day)))

    def next_session_open(self, after: datetime) -> datetime:
        """The next moment the market opens, strictly after `after`.

        Skips weekends and holidays. This is what FR-038 means by "the next
        session's open" — a decision reached on Friday's close fills on
        Monday, or on Tuesday if Monday is a holiday.
        """
        stamp = pd.Timestamp(after).tz_convert("UTC") if after.tzinfo else pd.Timestamp(after, tz="UTC")
        return self._cal.next_open(stamp).to_pydatetime().astimezone(UTC)

    def session_close(self, day: date) -> datetime:
        """Closing time, which is 1pm rather than 4pm on early-close days."""
        return self._cal.session_close(pd.Timestamp(day)).to_pydatetime().astimezone(UTC)

    def session_open(self, day: date) -> datetime:
        return self._cal.session_open(pd.Timestamp(day)).to_pydatetime().astimezone(UTC)

    def is_early_close(self, day: date) -> bool:
        """True on half-days, where a 4-hour bar has even less room than usual."""
        if not self.is_session(day):
            return False
        close = self.session_close(day)
        open_ = self.session_open(day)
        return (close - open_).total_seconds() < 6 * 3600

    def sessions_between(self, start: date, end: date) -> list[date]:
        sessions = self._cal.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
        return [s.date() for s in sessions]

    def missing_sessions(self, start: date, end: date, present: set[date]) -> list[date]:
        """Sessions the calendar expects but the data does not contain."""
        return [d for d in self.sessions_between(start, end) if d not in present]
