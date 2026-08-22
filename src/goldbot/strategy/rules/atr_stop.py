"""Volatility-based stops: place the invalidation level where noise cannot reach it."""

from __future__ import annotations

from decimal import Decimal

from goldbot.domain.bar import MarketView
from goldbot.domain.money import ZERO
from goldbot.domain.verdict import Verdict
from goldbot.strategy.indicators import atr
from goldbot.strategy.rule import insufficient_history


class AtrStop:
    """Stop distance scaled to how much this market is currently moving.

    A fixed percentage stop is wrong in both directions: too tight when
    volatility rises, needlessly wide when it falls. Scaling to ATR keeps the
    stop at the same *statistical* distance from price, so a stop is hit
    because the idea failed rather than because Tuesday was busy.

    The stop this rule computes lands in the verdict's evidence, which is where
    the setup picks it up to size the position.
    """

    rule_id = "atr_stop"
    principle = "volatility-based-stops"

    def __init__(self, lookback: int = 14, multiple: Decimal = Decimal("2.0")) -> None:
        self.lookback = lookback
        self.multiple = multiple

    def evaluate(self, view: MarketView) -> Verdict:
        needed = self.lookback + 1
        if not view.has(needed):
            return insufficient_history(self.rule_id, self.principle, needed, len(view))

        bars = view.window(needed)
        value = atr(bars, self.lookback)
        assert value is not None
        close = view[0].close
        distance = value * self.multiple
        stop = close - distance

        usable = stop > ZERO and distance > ZERO
        if not usable:
            return Verdict(
                rule_id=self.rule_id,
                principle=self.principle,
                passed=False,
                evidence={"close": close, "atr": value, "stop": stop},
                statement=(
                    f"An ATR of {value:.2f} puts the stop at {stop:.2f}, which is not a usable "
                    "level, so no position can be sized."
                ),
            )

        return Verdict(
            rule_id=self.rule_id,
            principle=self.principle,
            passed=True,
            evidence={
                "close": close,
                f"atr_{self.lookback}": value,
                "multiple": self.multiple,
                "stop": stop,
                "stop_distance": distance,
                "stop_distance_pct": distance / close,
            },
            statement=(
                f"Average true range over {self.lookback} days is {value:.2f}; at "
                f"{self.multiple}x that, the invalidation level sits at {stop:.2f}, "
                f"{distance:.2f} below the close ({distance / close:.2%})."
            ),
        )
