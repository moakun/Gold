"""Indicators, in exact decimal arithmetic over an explicit bar window.

No numpy, no vectorisation. At a few thousand daily bars the speed does not
matter, and what is gained is worth more than the microseconds: the arithmetic
is exact, the loops are readable by someone learning what an ATR actually is,
and two runs cannot disagree in the last decimal place.
"""

from __future__ import annotations

from decimal import Decimal

from goldbot.domain.bar import Bar
from goldbot.domain.money import ZERO


def sma(bars: tuple[Bar, ...], n: int) -> Decimal | None:
    """Simple moving average of closes. None when history is short."""
    if n <= 0:
        raise ValueError("period must be positive")
    if len(bars) < n:
        return None
    window = bars[-n:]
    return sum((bar.close for bar in window), ZERO) / n


def true_range(bar: Bar, previous: Bar | None) -> Decimal:
    """How far price actually travelled, counting the overnight gap.

    The gap term is the whole point for this instrument: the exchange is closed
    most of the day, so a measure using only the session's own high and low
    would understate risk badly.
    """
    if previous is None:
        return bar.high - bar.low
    return max(
        bar.high - bar.low,
        abs(bar.high - previous.close),
        abs(bar.low - previous.close),
    )


def atr(bars: tuple[Bar, ...], n: int) -> Decimal | None:
    """Average true range over the last `n` bars.

    A plain mean rather than Wilder's smoothing: it needs no seed value, so the
    result depends only on the window rather than on where the series started,
    which keeps backtests reproducible across different snapshot ranges.
    """
    if n <= 0:
        raise ValueError("period must be positive")
    if len(bars) < n + 1:
        return None
    ranges = [true_range(bars[i], bars[i - 1]) for i in range(len(bars) - n, len(bars))]
    return sum(ranges, ZERO) / n


def highest_close(bars: tuple[Bar, ...], n: int) -> Decimal | None:
    if len(bars) < n or n <= 0:
        return None
    return max(bar.close for bar in bars[-n:])


def lowest_close(bars: tuple[Bar, ...], n: int) -> Decimal | None:
    if len(bars) < n or n <= 0:
        return None
    return min(bar.close for bar in bars[-n:])


def highest_high(bars: tuple[Bar, ...], n: int) -> Decimal | None:
    if len(bars) < n or n <= 0:
        return None
    return max(bar.high for bar in bars[-n:])


def rate_of_change(bars: tuple[Bar, ...], n: int) -> Decimal | None:
    """Proportional change over `n` bars. 0.05 means five percent higher."""
    if len(bars) < n + 1 or n <= 0:
        return None
    then = bars[-1 - n].close
    if then <= ZERO:
        return None
    return (bars[-1].close - then) / then
