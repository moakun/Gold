"""Composing rules into a setup.

Every rule is evaluated. Not one of them is short-circuited, even after an
earlier rule has already failed.

That costs a little work and buys the thing this project exists for: to explain
why a setup was skipped you need to know which conditions *passed* as well as
the one that did not. "No trade because the trend filter failed" is a log line.
"Momentum and volatility were fine, the trend filter vetoed it" is a lesson.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from goldbot.domain.bar import MarketView
from goldbot.domain.verdict import Verdict
from goldbot.strategy.rules import AtrStop, EntryTrigger, EventBlackout, TrendExit, TrendFilter


@dataclass(frozen=True, slots=True)
class SetupResult:
    """Everything one evaluation of the rule set produced."""

    verdicts: tuple[Verdict, ...]
    stop: Decimal | None
    target: Decimal | None

    @property
    def all_passed(self) -> bool:
        return all(v.passed for v in self.verdicts)

    @property
    def blocking(self) -> Verdict | None:
        """The first failed verdict, in evaluation order. The one the journal leads with."""
        for verdict in self.verdicts:
            if not verdict.passed:
                return verdict
        return None


class EntrySetup:
    """The conditions that must all hold before a long is considered."""

    def __init__(
        self,
        *,
        trend_lookback: int = 100,
        momentum_lookback: int = 20,
        atr_lookback: int = 14,
        atr_multiple: Decimal = Decimal("2.0"),
        reward_risk_target: Decimal = Decimal("2.0"),
        blackout_dates: tuple[date, ...] = (),
        event_policy: str = "stand_aside",
    ) -> None:
        self.reward_risk_target = reward_risk_target
        # Evaluation order is the order a person would think in: is the tide
        # coming in, is there a signal, where would I be wrong, is today safe.
        self.rules = (
            TrendFilter(lookback=trend_lookback),
            EntryTrigger(lookback=momentum_lookback),
            AtrStop(lookback=atr_lookback, multiple=atr_multiple),
            EventBlackout(blackout_dates=blackout_dates, policy=event_policy),
        )

    def evaluate(self, view: MarketView) -> SetupResult:
        verdicts = tuple(rule.evaluate(view) for rule in self.rules)

        stop: Decimal | None = None
        target: Decimal | None = None
        for verdict in verdicts:
            if verdict.rule_id == "atr_stop" and verdict.passed:
                raw = verdict.evidence.get("stop")
                if isinstance(raw, Decimal):
                    stop = raw
                    distance = view[0].close - stop
                    target = view[0].close + distance * self.reward_risk_target

        return SetupResult(verdicts=verdicts, stop=stop, target=target)


class ExitSetup:
    """The conditions that end a trade for a reason other than the stop."""

    def __init__(self, *, lookback: int = 20) -> None:
        self.rules = (TrendExit(lookback=lookback),)

    def evaluate(self, view: MarketView) -> SetupResult:
        verdicts = tuple(rule.evaluate(view) for rule in self.rules)
        return SetupResult(verdicts=verdicts, stop=None, target=None)

    @staticmethod
    def should_exit(result: SetupResult) -> bool:
        """An exit rule passing means "leave", the opposite of an entry rule."""
        return any(v.passed for v in result.verdicts)
