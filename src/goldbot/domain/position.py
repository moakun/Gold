"""Positions and completed trades.

`Position` is frozen and deliberately incomplete: there is no `widen_stop`, no
`remove_stop`, and no `add_shares`. The constitution forbids those operations,
so rather than blocking them at runtime this type simply does not have them.
Calling one is an AttributeError while you are writing the code, which is a
much better time to find out than while you are losing money.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum

from goldbot.domain.errors import GuardViolation
from goldbot.domain.money import ZERO
from goldbot.domain.order import Fill


class ExitReason(str, Enum):
    STOP = "STOP"
    TARGET = "TARGET"
    RULE = "RULE"
    #: The market reopened below the stop. The fill is the open, not the stop.
    GAP_THROUGH_STOP = "GAP_THROUGH_STOP"
    KILL_SWITCH = "KILL_SWITCH"
    END_OF_DATA = "END_OF_DATA"


class LossClass(str, Enum):
    """Why a losing trade lost. The distinction most journals collapse."""

    #: Followed the rules and lost. The cost of doing business.
    CORRECT = "CORRECT"
    #: Lost because a rule was broken. A process failure, not a market outcome.
    RULE_VIOLATION = "RULE_VIOLATION"
    #: Lost because the system malfunctioned.
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass(frozen=True, slots=True)
class Position:
    """An open long exposure. Frozen, and missing the operations that lose accounts."""

    symbol: str
    shares: int
    entry_price: Decimal
    stop: Decimal
    opened_at: datetime
    opening_decision_id: str
    target: Decimal | None = None
    entry_costs: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.shares < 1:
            raise ValueError(f"{self.symbol}: a position needs at least one share")
        if self.stop >= self.entry_price:
            raise ValueError(
                f"{self.symbol}: stop {self.stop} is not below entry {self.entry_price}"
            )

    @property
    def initial_risk(self) -> Decimal:
        """What was at stake when the position opened. The denominator for R multiples."""
        return (self.entry_price - self.stop) * self.shares

    def unrealised(self, price: Decimal) -> Decimal:
        return (price - self.entry_price) * self.shares

    def tighten_stop(self, new_stop: Decimal) -> Position:
        """Move the stop closer to price. Refuses to move it away.

        Tightening is permitted because it reduces risk. Widening is the
        operation that turns a small planned loss into a large unplanned one,
        and it is refused here rather than merely discouraged.
        """
        if new_stop <= self.stop:
            raise GuardViolation(
                f"{self.symbol}: refusing to move the stop from {self.stop} to {new_stop}. "
                "A stop may only be tightened. Widening a stop after entry converts a "
                "planned loss into an open-ended one, and is forbidden by Principle I."
            )
        if new_stop >= self.entry_price:
            # Moving to breakeven or better is fine, but never above entry for a long
            # without the caller understanding it locks in a gain; allow it explicitly.
            pass
        return replace(self, stop=new_stop)


@dataclass(frozen=True, slots=True)
class Trade:
    """A completed round trip, judged honestly.

    `risk_overrun` is the field that keeps this system truthful. The market is
    closed roughly seventeen and a half hours a weekday, so a stop is an
    intention rather than a guarantee, and sometimes the fill is worse than
    planned. Recording that by how much is the difference between "the 1% rule
    held" as an assumption and as a measurement.
    """

    symbol: str
    entry_fill: Fill
    exit_fill: Fill
    shares: int
    exit_reason: ExitReason
    planned_risk: Decimal
    opening_decision_id: str
    closing_decision_id: str
    classification: LossClass | None = None

    @property
    def gross_result(self) -> Decimal:
        return (self.exit_fill.price - self.entry_fill.price) * self.shares

    @property
    def total_costs(self) -> Decimal:
        return self.entry_fill.costs.total + self.exit_fill.costs.total

    @property
    def result_currency(self) -> Decimal:
        """Net of every modelled cost. The only number worth reporting."""
        return self.gross_result - self.total_costs

    @property
    def result_r(self) -> Decimal:
        """Result in multiples of the risk originally taken."""
        if self.planned_risk <= ZERO:
            return ZERO
        return self.result_currency / self.planned_risk

    @property
    def risk_overrun(self) -> Decimal:
        """How much the realised loss exceeded the planned risk. Zero when it did not.

        Non-zero almost always means the market gapped through the stop
        overnight. A backtest reporting zero of these across years is not
        good news — it means the fill model is pretending stops always work.
        """
        loss = -self.result_currency
        if loss <= self.planned_risk:
            return ZERO
        return loss - self.planned_risk

    @property
    def is_win(self) -> bool:
        return self.result_currency > ZERO

    @property
    def held_days(self) -> int:
        return max(0, (self.exit_fill.at - self.entry_fill.at).days)
