"""Orders, and the capability token that is the only way to create one.

`Authorization` cannot be constructed directly. It is minted by
`goldbot.risk.gate` through `_mint_authorization`, and the simulated broker
accepts nothing else. That chain — verdicts make a decision, the gate turns a
decision into an authorization, the broker turns an authorization into a fill —
is how Principle I stops being a promise and starts being a type signature.

This is a guard, not a security boundary. Python cannot truly prevent a
determined caller from importing a private name. What it can do is make the
correct path the only obvious one and make the incorrect path fail a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum

from goldbot.domain.decision import EntryPlan
from goldbot.domain.errors import GuardViolation
from goldbot.domain.money import ZERO

#: The mint token. Only `goldbot.risk.gate` imports `_mint_authorization`, and
#: `tests/constitution/test_authorization_unforgeable.py` asserts that stays true.
_MINT_TOKEN = object()


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True, slots=True)
class Costs:
    """Itemised, never a single opaque number.

    Kept separate so a report can answer "where did the edge go?" — for a
    zero-commission ETF the answer is usually spread and slippage.
    """

    commission: Decimal = ZERO
    spread: Decimal = ZERO
    slippage: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.commission + self.spread + self.slippage

    def __add__(self, other: Costs) -> Costs:
        return Costs(
            commission=self.commission + other.commission,
            spread=self.spread + other.spread,
            slippage=self.slippage + other.slippage,
        )


@dataclass(frozen=True)
class Authorization:
    """Proof that the risk gate approved this trade.

    Direct construction raises. Use `goldbot.risk.gate.RiskGate.authorize`.
    """

    decision_id: str
    symbol: str
    side: Side
    plan: EntryPlan
    issued_at: datetime
    envelope_version: str
    _token: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._token is not _MINT_TOKEN:
            raise GuardViolation(
                "Authorization cannot be constructed directly. Every order must pass through "
                "RiskGate.authorize, which checks the allow-list, the stop, and the risk "
                "envelope before granting permission to trade."
            )
        object.__setattr__(self, "_token", None)


def _mint_authorization(
    *,
    decision_id: str,
    symbol: str,
    side: Side,
    plan: EntryPlan,
    issued_at: datetime,
    envelope_version: str,
) -> Authorization:
    """Private constructor for `Authorization`. Imported only by `goldbot.risk.gate`."""
    return Authorization(
        decision_id=decision_id,
        symbol=symbol,
        side=side,
        plan=plan,
        issued_at=issued_at,
        envelope_version=envelope_version,
        _token=_MINT_TOKEN,
    )


@dataclass(frozen=True, slots=True)
class Order:
    """An instruction to the (simulated) broker. Always carries its authorization."""

    id: str
    authorization: Authorization
    side: Side
    shares: int
    submitted_at: datetime
    #: Always True in this version. There is no live path (FR-024), and the
    #: audit schema carries a CHECK constraint saying so.
    simulated: bool = True

    def __post_init__(self) -> None:
        if self.shares < 1:
            raise ValueError(f"order {self.id}: shares must be positive, got {self.shares}")
        if not self.simulated:
            raise GuardViolation(
                "this version has no live execution path; every order is simulated"
            )

    @property
    def symbol(self) -> str:
        return self.authorization.symbol

    @property
    def decision_id(self) -> str:
        return self.authorization.decision_id


@dataclass(frozen=True, slots=True)
class Fill:
    """A simulated execution, with what it actually cost."""

    order_id: str
    decision_id: str
    symbol: str
    side: Side
    price: Decimal
    shares: int
    at: datetime
    costs: Costs
    #: Difference between the price that triggered the decision and the price
    #: obtained. Required by FR-038 because daily-bar decisions fill at the
    #: next session's open, which is never the trigger price.
    slippage_vs_intended: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.price <= 0:
            raise ValueError(f"fill {self.order_id}: price must be positive")
        if self.shares < 1:
            raise ValueError(f"fill {self.order_id}: shares must be positive")

    @property
    def gross_value(self) -> Decimal:
        return self.price * self.shares
