"""Principle IV: a rule that reaches past the decision bar must fail loudly.

This is the guard that stops the most common way a backtest lies. A strategy
that can see tomorrow's close produces beautiful, untradeable results, and the
mistake is nearly invisible in aggregate numbers — so it is prevented by a data
structure rather than by care.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from goldbot.domain.bar import Bar, MarketView
from goldbot.domain.errors import LookAheadError
from goldbot.domain.money import dec

pytestmark = pytest.mark.constitution


def make_bars(count: int) -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)
    bars = []
    for i in range(count):
        end = base + timedelta(days=i)
        bars.append(
            Bar(
                symbol="GLD",
                start=end - timedelta(hours=6, minutes=30),
                end=end,
                open=dec("200"),
                high=dec("202"),
                low=dec("199"),
                close=dec("201"),
                volume=1_000_000,
            )
        )
    return tuple(bars)


def test_negative_offset_is_the_future_and_raises() -> None:
    bars = make_bars(10)
    view = MarketView(bars, as_of=bars[-1].end)

    assert view[0].end == bars[-1].end, "offset 0 is the decision bar"
    assert view[1].end == bars[-2].end, "offset 1 steps one bar back"

    with pytest.raises(LookAheadError):
        view[-1]


def test_a_cheating_rule_cannot_read_tomorrow() -> None:
    """The realistic failure: a rule written to peek one bar ahead."""
    bars = make_bars(50)
    view = MarketView(bars[:30], as_of=bars[29].end)

    def cheating_rule(v: MarketView) -> object:
        return v[-1].close  # "tomorrow's close"

    with pytest.raises(LookAheadError):
        cheating_rule(view)


def test_view_refuses_construction_with_future_bars() -> None:
    bars = make_bars(10)
    with pytest.raises(LookAheadError):
        MarketView(bars, as_of=bars[5].end)


def test_at_refuses_a_future_timestamp() -> None:
    bars = make_bars(10)
    view = MarketView(bars[:5], as_of=bars[4].end)
    with pytest.raises(LookAheadError):
        view.at(bars[7].end)


def test_window_never_pads_short_history() -> None:
    """A rule needing 200 bars on bar 20 gets 20, and must handle it in its verdict."""
    bars = make_bars(20)
    view = MarketView(bars, as_of=bars[-1].end)
    assert len(view.window(200)) == 20
    assert view.has(200) is False
