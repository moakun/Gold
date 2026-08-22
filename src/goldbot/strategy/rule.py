"""The rule contract.

A rule returns exactly one `Verdict`, always. Not `None`, and it does not raise
for an ordinary "condition not met" — failing to meet a condition is a verdict
with `passed=False`, which is precisely what makes a skipped setup explainable
(FR-004).

Rules are pure functions of the `MarketView` they are handed. No I/O, no clock,
no randomness. `tests/constitution/test_rules_are_pure.py` enforces that.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from goldbot.domain.bar import MarketView
from goldbot.domain.verdict import Verdict


@runtime_checkable
class Rule(Protocol):
    """One condition, one verdict."""

    rule_id: str
    principle: str

    def evaluate(self, view: MarketView) -> Verdict: ...


def insufficient_history(rule_id: str, principle: str, needed: int, have: int) -> Verdict:
    """The verdict every rule returns when the window is too short.

    Shared because it happens on the first hundred bars of every backtest, and
    because "not enough history yet" is a real answer to "why no trade today?"
    that the journal should give in those words.
    """
    return Verdict(
        rule_id=rule_id,
        principle=principle,
        passed=False,
        evidence={"bars_needed": needed, "bars_available": have},
        statement=(
            f"Not enough history yet: this rule needs {needed} bars and only {have} "
            "are available, so it cannot judge."
        ),
    )
