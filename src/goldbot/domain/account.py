"""What the risk gate needs to know about the account before it approves anything."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from goldbot.domain.money import ZERO
from goldbot.domain.position import Position


@dataclass(frozen=True, slots=True)
class AccountState:
    """A snapshot of the account at one decision point.

    `realised_today` is the basis for the daily loss halt, and it is realised
    rather than unrealised on purpose: a multi-day swing position would trip
    the halt on ordinary fluctuation otherwise, and the open position's stop is
    already the control for that exposure.
    """

    equity: Decimal
    cash: Decimal
    session: date
    realised_today: Decimal = ZERO
    positions: tuple[Position, ...] = field(default_factory=tuple)
    halted: bool = False
    halt_reason: str = ""

    @property
    def open_count(self) -> int:
        return len(self.positions)

    @property
    def is_flat(self) -> bool:
        return not self.positions

    def position_for(self, symbol: str) -> Position | None:
        for position in self.positions:
            if position.symbol.upper() == symbol.upper():
                return position
        return None

    def daily_loss_fraction(self) -> Decimal:
        """Realised loss today as a fraction of equity. Zero when up on the day."""
        if self.equity <= ZERO or self.realised_today >= ZERO:
            return ZERO
        return -self.realised_today / self.equity
