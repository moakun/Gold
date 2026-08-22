"""Event risk: scheduled releases get a policy, not a shrug."""

from __future__ import annotations

from datetime import date

from goldbot.domain.bar import MarketView
from goldbot.domain.verdict import Verdict


class EventBlackout:
    """Stand aside into scheduled high-impact releases.

    Rate decisions, inflation prints, and employment reports move gold on
    information the strategy has no view on. Holding through one is not
    trading, it is a coin flip with leverage — so FR-019 requires an explicit
    policy, and this rule is it.

    The list is configured rather than fetched, because a rule that phones a
    calendar API is no longer a pure function of the market.
    """

    rule_id = "event_blackout"
    principle = "event-risk"

    def __init__(self, blackout_dates: tuple[date, ...] = (), policy: str = "stand_aside") -> None:
        self.blackout_dates = frozenset(blackout_dates)
        self.policy = policy

    def evaluate(self, view: MarketView) -> Verdict:
        today = view[0].end.date()
        in_blackout = today in self.blackout_dates

        if self.policy == "trade":
            return Verdict(
                rule_id=self.rule_id,
                principle=self.principle,
                passed=True,
                evidence={"policy": self.policy, "date": today.isoformat()},
                statement=(
                    "The configured event policy is to trade through scheduled releases, "
                    "so event risk does not veto this setup."
                ),
            )

        if in_blackout:
            return Verdict(
                rule_id=self.rule_id,
                principle=self.principle,
                passed=False,
                evidence={
                    "policy": self.policy,
                    "date": today.isoformat(),
                    "blackout": True,
                },
                statement=(
                    f"{today.isoformat()} is a scheduled high-impact event date and the "
                    "policy is to stand aside; the outcome of a release is not something "
                    "this strategy has an edge on."
                ),
            )

        return Verdict(
            rule_id=self.rule_id,
            principle=self.principle,
            passed=True,
            evidence={
                "policy": self.policy,
                "date": today.isoformat(),
                "blackout": False,
            },
            statement=(
                f"No scheduled high-impact event on {today.isoformat()}, so nothing on the "
                "calendar argues against taking a signal today."
            ),
        )
