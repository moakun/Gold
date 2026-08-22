"""Momentum confirmation: wait for the market to prove itself before buying."""

from __future__ import annotations

from goldbot.domain.bar import MarketView
from goldbot.domain.verdict import Verdict
from goldbot.strategy.indicators import highest_close
from goldbot.strategy.rule import insufficient_history


class EntryTrigger:
    """A close at the highest level of the recent window.

    Buying a breakout means paying up rather than buying a dip. The trade-off
    is deliberate: it gives up entry price in exchange for evidence that buyers
    are actually in control, which is what keeps this out of long slow declines
    that look cheap the whole way down.
    """

    rule_id = "entry_trigger"
    principle = "momentum-confirmation"

    def __init__(self, lookback: int = 20) -> None:
        self.lookback = lookback

    def evaluate(self, view: MarketView) -> Verdict:
        needed = self.lookback + 1
        if not view.has(needed):
            return insufficient_history(self.rule_id, self.principle, needed, len(view))

        close = view[0].close
        # The prior window, excluding today, so "a new high" means new.
        prior = view.window(needed)[:-1]
        prior_high = highest_close(prior, self.lookback)
        assert prior_high is not None
        broke_out = close > prior_high

        return Verdict(
            rule_id=self.rule_id,
            principle=self.principle,
            passed=broke_out,
            evidence={
                "close": close,
                f"prior_{self.lookback}_day_high_close": prior_high,
                "margin": close - prior_high,
            },
            statement=(
                f"Close {close:.2f} is a new {self.lookback}-day closing high, above the "
                f"previous best of {prior_high:.2f}."
                if broke_out
                else (
                    f"Close {close:.2f} is below the {self.lookback}-day closing high of "
                    f"{prior_high:.2f}, so buyers have not yet proved control."
                )
            ),
        )
