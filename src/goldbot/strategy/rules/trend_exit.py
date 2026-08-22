"""Exit discipline: a reason to leave that is not the stop."""

from __future__ import annotations

from goldbot.domain.bar import MarketView
from goldbot.domain.verdict import Verdict
from goldbot.strategy.indicators import sma
from goldbot.strategy.rule import insufficient_history


class TrendExit:
    """Leave when the shorter-term trend gives way.

    A stop answers "was I wrong?". This answers "is the reason I entered still
    true?" — a different question, and the one that separates a trade that ran
    its course from a trade that failed. Without it every winner is held until
    it becomes a loser, which is the most reliable way to turn a decent
    strategy into a poor one.
    """

    rule_id = "trend_exit"
    principle = "exit-discipline"

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = lookback

    def evaluate(self, view: MarketView) -> Verdict:
        if not view.has(self.lookback):
            return insufficient_history(self.rule_id, self.principle, self.lookback, len(view))

        bars = view.window(self.lookback)
        average = sma(bars, self.lookback)
        assert average is not None
        close = view[0].close
        broken = close < average

        return Verdict(
            rule_id=self.rule_id,
            principle=self.principle,
            passed=broken,
            evidence={"close": close, f"sma_{self.lookback}": average},
            statement=(
                f"Close {close:.2f} has slipped below its {self.lookback}-day average of "
                f"{average:.2f}; the move that justified the entry is over."
                if broken
                else (
                    f"Close {close:.2f} still holds above its {self.lookback}-day average of "
                    f"{average:.2f}, so the reason for being in the trade stands."
                )
            ),
        )
