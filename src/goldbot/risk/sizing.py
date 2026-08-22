"""Turning a stop into a position size.

Two constraints compete and either can bind first. A tight stop makes the risk
budget permissive but consumes cash: a $10,000 account risking 1% ($100) with a
$3 stop wants 33 shares, which at $300 a share costs $9,900 of the $10,000
available. Cash binds, not risk — and the operator deserves to be told which.

Shares are whole numbers, so sizing rounds down and actual risk lands at or
below the limit, never above.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from goldbot.domain.decision import Constraint
from goldbot.domain.money import ZERO, dec


@dataclass(frozen=True, slots=True)
class SizingResult:
    """How many shares, and which limit decided."""

    shares: int
    risk_amount: Decimal
    risk_pct: Decimal
    binding_constraint: Constraint
    #: Populated when shares is zero, so the skip can explain itself.
    reason: str = ""

    @property
    def is_tradable(self) -> bool:
        return self.shares >= 1


def size_position(
    *,
    entry: Decimal,
    stop: Decimal,
    equity: Decimal,
    cash: Decimal,
    max_risk_per_trade: Decimal,
) -> SizingResult:
    """Size a long position from its stop distance.

    Returns a result with zero shares and a reason rather than raising, because
    "too small to trade" is an ordinary outcome that the journal should explain,
    not an error.
    """
    if entry <= ZERO:
        raise ValueError(f"entry price must be positive, got {entry}")
    if stop >= entry:
        raise ValueError(
            f"stop {stop} must sit below entry {entry}; this system is long-only"
        )
    if equity <= ZERO:
        return SizingResult(0, ZERO, ZERO, Constraint.NONE, "account equity is zero or negative")

    stop_distance = entry - stop
    risk_budget = equity * max_risk_per_trade

    shares_by_risk = int((risk_budget / stop_distance).to_integral_value(rounding=ROUND_DOWN))
    shares_by_cash = int((cash / entry).to_integral_value(rounding=ROUND_DOWN))

    shares = min(shares_by_risk, shares_by_cash)

    if shares < 1:
        if shares_by_risk < 1:
            reason = (
                f"a single share would risk {stop_distance:.2f} against a budget of "
                f"{risk_budget:.2f} ({max_risk_per_trade:.2%} of {equity:.2f}), so the "
                "smallest tradable size exceeds the per-trade limit"
            )
            binding = Constraint.RISK_BUDGET
        else:
            reason = (
                f"cash of {cash:.2f} will not buy one share at {entry:.2f}"
            )
            binding = Constraint.AVAILABLE_CASH
        return SizingResult(0, ZERO, ZERO, binding, reason)

    binding = (
        Constraint.RISK_BUDGET if shares_by_risk <= shares_by_cash else Constraint.AVAILABLE_CASH
    )
    risk_amount = stop_distance * shares
    risk_pct = risk_amount / equity

    return SizingResult(
        shares=shares,
        risk_amount=risk_amount,
        risk_pct=risk_pct,
        binding_constraint=binding,
    )


def describe_sizing(result: SizingResult, entry: Decimal, stop: Decimal) -> str:
    """One line for the journal, naming the constraint that bound."""
    if not result.is_tradable:
        return f"No position: {result.reason}."
    bound = {
        Constraint.RISK_BUDGET: "the risk budget",
        Constraint.AVAILABLE_CASH: "available cash",
        Constraint.NONE: "no constraint",
    }[result.binding_constraint]
    return (
        f"{result.shares} shares at {entry:.2f} with a stop at {stop:.2f} risks "
        f"{result.risk_amount:.2f} ({result.risk_pct:.2%} of equity); size was set by {bound}."
    )


__all__ = ["SizingResult", "size_position", "describe_sizing", "dec"]
