"""Where bars come from, and what the engine is allowed to receive.

Two rules the feed enforces so the engine never has to remember them:

  * only completed bars reach the engine — partial bars are filtered here
  * gaps are reported, never interpolated

A fabricated bar is worse than a missing one. A missing bar shows up as a gap
in the journal; a fabricated one shows up as a profitable trade that never
existed.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from goldbot.domain.bar import Bar


@dataclass(frozen=True, slots=True)
class DataGap:
    """A stretch of missing sessions, surfaced rather than filled in."""

    after: date
    before: date
    missing_sessions: int

    def describe(self) -> str:
        return (
            f"{self.missing_sessions} session(s) missing between {self.after} and {self.before}"
        )


class DataFeed(Protocol):
    """The seam between "where data comes from" and "what the engine sees"."""

    def bars(self) -> Iterator[Bar]: ...

    def snapshot_digest(self) -> str | None: ...


def detect_gaps(bars: tuple[Bar, ...], max_normal_gap_days: int = 4) -> tuple[DataGap, ...]:
    """Find stretches of missing sessions.

    Four days is the normal maximum for a long weekend with a holiday attached.
    Anything longer is reported. This is heuristic on purpose — the exchange
    calendar knows the truth, but a feed should be able to flag suspicious data
    without one.
    """
    gaps: list[DataGap] = []
    for previous, current in zip(bars, bars[1:], strict=False):
        delta = (current.end.date() - previous.end.date()).days
        if delta > max_normal_gap_days:
            business_days = sum(
                1
                for offset in range(1, delta)
                if (previous.end.date() + timedelta(days=offset)).weekday() < 5
            )
            gaps.append(
                DataGap(
                    after=previous.end.date(),
                    before=current.end.date(),
                    missing_sessions=business_days,
                )
            )
    return tuple(gaps)


class HistoricalFeed:
    """Replays a pinned snapshot. The only feed a backtest may use."""

    def __init__(self, bars: tuple[Bar, ...], digest: str) -> None:
        if not digest:
            raise ValueError(
                "a historical feed needs a snapshot digest; an unpinned backtest is not "
                "reproducible and must not run"
            )
        self._bars = tuple(bar for bar in bars if bar.is_complete)
        self._digest = digest
        self.gaps = detect_gaps(self._bars)

    def bars(self) -> Iterator[Bar]:
        yield from self._bars

    def snapshot_digest(self) -> str | None:
        return self._digest

    def __len__(self) -> int:
        return len(self._bars)

    @property
    def all_bars(self) -> tuple[Bar, ...]:
        return self._bars
