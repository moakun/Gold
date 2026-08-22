"""Trend alignment: only consider longs while the long-term trend is up."""

from __future__ import annotations

from goldbot.domain.bar import MarketView
from goldbot.domain.verdict import Verdict
from goldbot.strategy.indicators import sma
from goldbot.strategy.rule import insufficient_history


class TrendFilter:
    """Price above its long moving average, or no long is considered.

    The cheapest risk control there is. It does not predict anything — it just
    declines to fight a downtrend, which removes a large share of the worst
    trades at the cost of missing the first part of every recovery.
    """

    rule_id = "trend_filter"
    principle = "trend-alignment"

    def __init__(self, lookback: int = 100) -> None:
        self.lookback = lookback

    def evaluate(self, view: MarketView) -> Verdict:
        if not view.has(self.lookback):
            return insufficient_history(self.rule_id, self.principle, self.lookback, len(view))

        bars = view.window(self.lookback)
        average = sma(bars, self.lookback)
        assert average is not None
        close = view[0].close
        aligned = close > average
        distance = (close - average) / average

        return Verdict(
            rule_id=self.rule_id,
            principle=self.principle,
            passed=aligned,
            evidence={
                "close": close,
                f"sma_{self.lookback}": average,
                "distance_pct": distance,
            },
            statement=(
                f"Close {close:.2f} is {'above' if aligned else 'below'} its "
                f"{self.lookback}-day average of {average:.2f} "
                f"({distance:+.2%}), so the long-term trend is "
                f"{'up and longs are allowed' if aligned else 'down and no long is considered'}."
            ),
        )
