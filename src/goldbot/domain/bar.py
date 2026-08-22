"""Price bars, and the bounded window a rule is allowed to see.

`MarketView` is the most important type in this module. It is what turns
"do not use future data" from a code-review comment into something that raises.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from goldbot.domain.errors import DataIntegrityError, LookAheadError


@dataclass(frozen=True, slots=True)
class Bar:
    """One completed period of price history.

    A bar that fails validation is a data defect, not a trading signal. It
    raises rather than being quietly dropped, because a silently skipped bar
    changes results without telling anyone.
    """

    symbol: str
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    is_complete: bool = True

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise DataIntegrityError(f"{self.symbol} bar timestamps must be timezone-aware")
        if self.start >= self.end:
            raise DataIntegrityError(
                f"{self.symbol} bar starts at or after it ends: {self.start} -> {self.end}"
            )
        for name, value in (
            ("open", self.open),
            ("high", self.high),
            ("low", self.low),
            ("close", self.close),
        ):
            if value <= 0:
                raise DataIntegrityError(f"{self.symbol} bar at {self.end}: {name} is {value}")
        if self.low > self.high:
            raise DataIntegrityError(
                f"{self.symbol} bar at {self.end}: low {self.low} exceeds high {self.high}"
            )
        if not (self.low <= self.open <= self.high):
            raise DataIntegrityError(
                f"{self.symbol} bar at {self.end}: open {self.open} outside "
                f"[{self.low}, {self.high}]"
            )
        if not (self.low <= self.close <= self.high):
            raise DataIntegrityError(
                f"{self.symbol} bar at {self.end}: close {self.close} outside "
                f"[{self.low}, {self.high}]"
            )
        if self.volume < 0:
            raise DataIntegrityError(f"{self.symbol} bar at {self.end}: negative volume")

    @property
    def range(self) -> Decimal:
        """High minus low. The bar's own measure of the day's disagreement."""
        return self.high - self.low


class MarketView:
    """Everything a rule is allowed to know at one moment in time.

    **Indexing runs backwards from the decision bar**, which is unusual and
    deliberate:

        view[0]   the bar being decided on (today)
        view[1]   the bar before it (yesterday)
        view[-1]  tomorrow -> LookAheadError

    Reversing the usual convention makes "the future" the negative direction,
    so a rule that reaches forward fails loudly instead of quietly returning
    the wrong bar. Chronological order is available through `window()`, which
    is what indicator maths wants.
    """

    __slots__ = ("_bars", "as_of")

    def __init__(self, bars: tuple[Bar, ...], as_of: datetime) -> None:
        if not bars:
            raise ValueError("a MarketView needs at least one bar")
        if any(bar.end > as_of for bar in bars):
            raise LookAheadError(
                f"MarketView built with bars ending after as_of={as_of.isoformat()}"
            )
        self._bars = bars
        self.as_of = as_of

    def __len__(self) -> int:
        return len(self._bars)

    def __getitem__(self, offset: int) -> Bar:
        """`view[0]` is the decision bar; larger offsets step backwards in time."""
        if offset < 0:
            raise LookAheadError(
                f"offset {offset} asks for a bar after the decision bar at "
                f"{self.as_of.isoformat()}; the future is not observable here"
            )
        if offset >= len(self._bars):
            raise IndexError(
                f"offset {offset} reaches before the start of available history "
                f"({len(self._bars)} bars)"
            )
        return self._bars[-1 - offset]

    def window(self, n: int) -> tuple[Bar, ...]:
        """The most recent `n` bars in chronological order, oldest first.

        Returns fewer than `n` when history is short. It never pads — a rule
        needing 200 bars on bar 50 gets 50 and must say so in its verdict.
        """
        if n <= 0:
            raise ValueError(f"window size must be positive, got {n}")
        return self._bars[-n:]

    def latest(self) -> Bar:
        """The bar being decided on."""
        return self._bars[-1]

    def has(self, n: int) -> bool:
        """True when at least `n` bars of history are available."""
        return len(self._bars) >= n

    def at(self, when: datetime) -> Bar:
        """The bar ending at `when`. Raises if `when` is in the future."""
        if when > self.as_of:
            raise LookAheadError(
                f"bar at {when.isoformat()} is after the decision bar at {self.as_of.isoformat()}"
            )
        for bar in reversed(self._bars):
            if bar.end == when:
                return bar
        raise KeyError(f"no bar ends at {when.isoformat()}")
