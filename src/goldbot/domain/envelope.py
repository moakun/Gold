"""The binding risk limits.

Defaults come from the constitution. They are content-hashed so that every
authorization records exactly which limits were in force when it was granted,
and immutable during a run so that nobody can loosen them mid-session (FR-018).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal

from goldbot.domain.money import dec


@dataclass(frozen=True, slots=True)
class RiskEnvelope:
    """Constitution defaults: 1% per trade, 3% daily halt, one position at a time."""

    max_risk_per_trade: Decimal = dec("0.010")
    max_daily_loss: Decimal = dec("0.030")
    max_concurrent_positions: int = 1
    #: Never binding in a cash account, kept because the constitution sets it
    #: and a future instrument might reach it.
    max_leverage: Decimal = dec("2.0")

    def __post_init__(self) -> None:
        if not (0 < self.max_risk_per_trade <= 1):
            raise ValueError(
                f"max_risk_per_trade must be a fraction in (0, 1], got {self.max_risk_per_trade}"
            )
        if not (0 < self.max_daily_loss <= 1):
            raise ValueError(
                f"max_daily_loss must be a fraction in (0, 1], got {self.max_daily_loss}"
            )
        if self.max_risk_per_trade > self.max_daily_loss:
            raise ValueError(
                f"per-trade risk {self.max_risk_per_trade} exceeds the daily loss limit "
                f"{self.max_daily_loss}; one losing trade would trip the halt"
            )
        if self.max_concurrent_positions < 1:
            raise ValueError("max_concurrent_positions must be at least 1")
        if self.max_leverage < 1:
            raise ValueError("max_leverage must be at least 1")

    @property
    def version(self) -> str:
        """Content hash. Recorded on every authorization."""
        payload = "|".join(
            [
                str(self.max_risk_per_trade),
                str(self.max_daily_loss),
                str(self.max_concurrent_positions),
                str(self.max_leverage),
            ]
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:12]

    def describe(self) -> str:
        return (
            f"{self.max_risk_per_trade:.2%} per trade, "
            f"{self.max_daily_loss:.2%} daily halt, "
            f"max {self.max_concurrent_positions} position(s)"
        )
