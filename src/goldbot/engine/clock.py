"""Time, injected rather than read.

The historical clock derives every timestamp from the bar being processed. That
is what lets two runs of the same snapshot produce identical journals — nothing
in the decision path can ask the operating system what time it is.

`engine/clock.py` is the one module exempted from the no-wall-clock guard,
because reading real time is precisely what a live clock is for.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from goldbot.domain.bar import Bar


class Clock(Protocol):
    def now(self) -> datetime: ...


class HistoricalClock:
    """Time as the bar sequence sees it."""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def advance_to(self, bar: Bar) -> None:
        self._now = bar.end

    def now(self) -> datetime:
        return self._now


class LiveClock:
    """Real time, in UTC. The only place the system reads the system clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)
