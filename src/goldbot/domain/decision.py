"""The central artifact: one decision per market evaluation, reasoning attached.

`Decision` refuses to exist without verdicts. That single constructor check is
what makes FR-006 — "block any order for which an explanation cannot be
produced" — structural rather than aspirational: there is no path that reaches
an order without the reasoning, because the reasoning is a constructor argument.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from goldbot.domain.money import ZERO
from goldbot.domain.verdict import Verdict


class Action(str, Enum):
    ENTER = "ENTER"
    EXIT = "EXIT"
    HOLD = "HOLD"
    SKIP = "SKIP"


class Constraint(str, Enum):
    """Which limit determined the position size."""

    RISK_BUDGET = "RISK_BUDGET"
    AVAILABLE_CASH = "AVAILABLE_CASH"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class EntryPlan:
    """Everything FR-003 requires an entry to state before it is allowed to happen."""

    intended_entry: Decimal
    stop: Decimal
    shares: int
    risk_amount: Decimal
    risk_pct: Decimal
    binding_constraint: Constraint
    target: Decimal | None = None

    def __post_init__(self) -> None:
        if self.stop >= self.intended_entry:
            raise ValueError(
                f"stop {self.stop} must sit below entry {self.intended_entry}; "
                "this system is long-only, so a stop above entry is not a stop"
            )
        if self.shares < 1:
            raise ValueError(f"an entry plan needs at least one share, got {self.shares}")
        expected = self.shares * (self.intended_entry - self.stop)
        if abs(self.risk_amount - expected) > Decimal("0.01"):
            raise ValueError(
                f"risk_amount {self.risk_amount} disagrees with shares x stop distance "
                f"({expected}); the plan is internally inconsistent"
            )
        if self.risk_pct <= 0:
            raise ValueError("risk_pct must be positive")
        if self.target is not None and self.target <= self.intended_entry:
            raise ValueError(
                f"target {self.target} must sit above entry {self.intended_entry} for a long"
            )

    @property
    def stop_distance(self) -> Decimal:
        return self.intended_entry - self.stop

    @property
    def reward_risk(self) -> Decimal | None:
        """Reward-to-risk, or None when no target is set."""
        if self.target is None:
            return None
        distance = self.stop_distance
        if distance <= ZERO:
            return None
        return (self.target - self.intended_entry) / distance


@dataclass(frozen=True)
class Decision:
    """One market evaluation and the reasoning behind it.

    Constructed for every completed bar, including the many where nothing
    happens. A no-trade decision with no explanation is exactly the thing this
    project exists to prevent.
    """

    as_of: datetime
    symbol: str
    action: Action
    verdicts: tuple[Verdict, ...]
    explanation: str
    run_id: str = ""
    plan: EntryPlan | None = None
    blocking_verdict: Verdict | None = None

    def __post_init__(self) -> None:
        if not self.verdicts:
            raise ValueError(
                f"{self.symbol} at {self.as_of.isoformat()}: a decision cannot exist without "
                "verdicts; every decision this system makes must be explainable"
            )
        if not self.explanation.strip():
            raise ValueError(
                f"{self.symbol} at {self.as_of.isoformat()}: a decision must carry a "
                "plain-language explanation"
            )
        if self.action is Action.ENTER and self.plan is None:
            raise ValueError(
                f"{self.symbol} at {self.as_of.isoformat()}: an entry needs a plan stating "
                "its stop, size, risk, and reward-to-risk"
            )
        if self.action is Action.SKIP and self.blocking_verdict is None:
            raise ValueError(
                f"{self.symbol} at {self.as_of.isoformat()}: a skip must name the condition "
                "that vetoed it, otherwise it teaches nothing"
            )
        if self.blocking_verdict is not None and self.blocking_verdict.passed:
            raise ValueError(
                f"{self.symbol} at {self.as_of.isoformat()}: the blocking verdict "
                f"{self.blocking_verdict.rule_id} is marked as passed"
            )

    @property
    def id(self) -> str:
        """Deterministic identifier: same run, same bar, same id."""
        payload = f"{self.run_id}|{self.symbol}|{self.as_of.isoformat()}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    @property
    def principles(self) -> tuple[str, ...]:
        """Every principle touched by this decision, in evaluation order, deduplicated."""
        seen: dict[str, None] = {}
        for verdict in self.verdicts:
            seen.setdefault(verdict.principle, None)
        return tuple(seen)

    def failed_verdicts(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if not v.passed)

    def passed_verdicts(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.passed)
