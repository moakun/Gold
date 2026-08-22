"""The only broker.

There is no live counterpart, and that is the point (FR-024). Fills are
computed here, in process, from the bars the feed produced.

**Cost convention.** `Fill.price` is the market reference price obtained — the
session open for an entry, the stop level for a stop exit. Spread and slippage
are charged as explicit cash costs alongside it rather than folded into the
price, so a report can answer "where did the edge go?" instead of just showing
a worse number. Charging them twice, once in the price and once as a cost,
would understate every result; charging them nowhere would flatter every result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from goldbot.domain.bar import Bar
from goldbot.domain.instrument import Instrument
from goldbot.domain.money import ZERO, dec
from goldbot.domain.order import Authorization, Costs, Fill, Order, Side
from goldbot.domain.position import ExitReason, Position

BPS = dec("10000")


@dataclass(frozen=True, slots=True)
class ExitSignal:
    """A stop or target that the current bar would have triggered."""

    price: Decimal
    reason: ExitReason


class SimulatedBroker:
    """Turns an authorization into a fill, and a bar into an exit."""

    def __init__(self, instrument: Instrument) -> None:
        self.instrument = instrument
        self._sequence = 0

    def _next_id(self, prefix: str) -> str:
        self._sequence += 1
        return f"{prefix}-{self._sequence:06d}"

    def _costs(self, price: Decimal, shares: int) -> Costs:
        notional = price * shares
        spread = notional * self.instrument.half_spread_bps / BPS
        slippage = notional * self.instrument.slippage_bps / BPS
        commission = self.instrument.commission_per_share * shares
        if commission > ZERO:
            commission = max(commission, self.instrument.commission_minimum)
        return Costs(commission=commission, spread=spread, slippage=slippage)

    # -- entries ----------------------------------------------------------

    def submit_entry(
        self, authorization: Authorization, *, bar: Bar, at: datetime
    ) -> tuple[Order, Fill]:
        """Fill a buy at the session open.

        The decision was made on a completed bar while the market was shut, so
        this is the first price actually available (FR-038). It is almost never
        the price that triggered the decision, and the difference is recorded.
        """
        if not isinstance(authorization, Authorization):
            raise TypeError(
                "the broker accepts only an Authorization minted by RiskGate; "
                f"got {type(authorization).__name__}"
            )

        plan = authorization.plan
        order = Order(
            id=self._next_id("ord"),
            authorization=authorization,
            side=Side.BUY,
            shares=plan.shares,
            submitted_at=at,
        )
        price = bar.open
        fill = Fill(
            order_id=order.id,
            decision_id=authorization.decision_id,
            symbol=authorization.symbol,
            side=Side.BUY,
            price=price,
            shares=plan.shares,
            at=bar.start,
            costs=self._costs(price, plan.shares),
            slippage_vs_intended=price - plan.intended_entry,
        )
        return order, fill

    # -- exits ------------------------------------------------------------

    def check_exit(self, position: Position, bar: Bar, target: Decimal | None) -> ExitSignal | None:
        """Would this bar have taken us out, and at what price?

        Order of checks is deliberately pessimistic:

        1. **Gap through the stop.** The open is already below the stop, so the
           fill is the open. This is the honest case for an instrument that is
           shut most of the day, and it is where planned risk gets exceeded.
        2. **Stop touched intrabar.** Fill at the stop.
        3. **Target touched intrabar.** Fill at the target.

        When a bar's range covers both the stop and the target, the stop wins.
        Daily bars cannot say which came first, and assuming the good outcome
        would quietly inflate every result in the report.
        """
        if bar.open <= position.stop:
            return ExitSignal(price=bar.open, reason=ExitReason.GAP_THROUGH_STOP)
        if bar.low <= position.stop:
            return ExitSignal(price=position.stop, reason=ExitReason.STOP)
        if target is not None and bar.high >= target:
            return ExitSignal(price=target, reason=ExitReason.TARGET)
        return None

    def submit_exit(
        self,
        position: Position,
        *,
        price: Decimal,
        shares: int,
        at: datetime,
        decision_id: str,
        intended: Decimal | None = None,
    ) -> Fill:
        return Fill(
            order_id=self._next_id("exit"),
            decision_id=decision_id,
            symbol=position.symbol,
            side=Side.SELL,
            price=price,
            shares=shares,
            at=at,
            costs=self._costs(price, shares),
            slippage_vs_intended=(price - intended) if intended is not None else ZERO,
        )
