"""The tradable universe, and the fact that it is a closed list.

Principle II is enforced here and in `risk.gate`: an instrument that is not on
this list cannot be traded, and adding one is a code change with a test, not a
configuration tweak someone makes at 3am.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from goldbot.domain.errors import GuardViolation
from goldbot.domain.money import ZERO, dec


@dataclass(frozen=True, slots=True)
class Instrument:
    """A gold ETF share symbol and everything the cost model needs to know."""

    symbol: str
    name: str
    calendar: str = "XNYS"
    #: Disclosed in reports, deliberately NOT charged as a cost. A
    #: physically-backed fund pays its fee by selling metal, so the drag is
    #: already inside the share price this system trades. See research.md R10.
    expense_ratio: Decimal = dec("0.0040")
    commission_per_share: Decimal = ZERO
    commission_minimum: Decimal = ZERO
    #: Half-spread charged on entry and exit, as a fraction of price.
    half_spread_bps: Decimal = dec("1.0")
    #: Additional adverse move assumed on every fill, as a fraction of price.
    slippage_bps: Decimal = dec("2.0")

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("an instrument needs a symbol")
        if self.expense_ratio < 0:
            raise ValueError(f"{self.symbol}: negative expense ratio")
        for name, value in (
            ("half_spread_bps", self.half_spread_bps),
            ("slippage_bps", self.slippage_bps),
        ):
            if value < 0:
                raise ValueError(f"{self.symbol}: {name} may not be negative")


class AllowList:
    """The closed set of instruments this system may trade.

    Fails closed: `require()` raises for anything absent, and there is no
    method that adds to the list at runtime.
    """

    __slots__ = ("_by_symbol",)

    def __init__(self, instruments: tuple[Instrument, ...]) -> None:
        if not instruments:
            raise ValueError("the allow-list may not be empty")
        self._by_symbol = {i.symbol.upper(): i for i in instruments}

    def __contains__(self, symbol: object) -> bool:
        return isinstance(symbol, str) and symbol.upper() in self._by_symbol

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self._by_symbol.values())

    def __len__(self) -> int:
        return len(self._by_symbol)

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_symbol))

    def get(self, symbol: str) -> Instrument | None:
        return self._by_symbol.get(symbol.upper())

    def require(self, symbol: str) -> Instrument:
        """Return the instrument, or refuse.

        This is the fail-closed path for Principle II.
        """
        found = self._by_symbol.get(symbol.upper())
        if found is None:
            raise GuardViolation(
                f"{symbol!r} is not on the gold allow-list {self.symbols}; "
                "this system trades gold and nothing else"
            )
        return found
