"""The single decision loop.

Backtest and paper trading run through this same code. Only the feed and the
clock differ, which is what stops the two from quietly diverging — a strategy
cannot behave one way in simulation and another way live if there is only one
implementation of "behave".

**Ordering within a bar** is the part that has to be right, because getting it
wrong is how a backtest starts lying:

    1. fill any entry authorised yesterday, at today's open
    2. check whether today's range took the position out (gap, stop, target)
    3. build a MarketView ending at today's close
    4. decide — using only what step 3 can see
    5. authorise tomorrow's action, if any

Steps 4 and 5 happen after the close. Nothing decided today can act today. That
is FR-038, and it is also just what actually happens when you trade an exchange
that is shut when you do your analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from goldbot.config import Config
from goldbot.domain.account import AccountState
from goldbot.domain.bar import Bar, MarketView
from goldbot.domain.decision import Action, Decision, EntryPlan
from goldbot.domain.money import ZERO
from goldbot.domain.order import Authorization, Fill
from goldbot.domain.position import ExitReason, LossClass, Position, Trade
from goldbot.domain.verdict import Rejection, Verdict
from goldbot.execution.simulated import SimulatedBroker
from goldbot.journal.explain import explain
from goldbot.journal.store import AuditStore
from goldbot.risk.gate import RiskGate
from goldbot.risk.sizing import size_position
from goldbot.strategy.setup import EntrySetup, ExitSetup


def verdict_from_rejection(rejection: Rejection, principle: str) -> Verdict:
    """Turn a risk refusal into something the journal can render as a decision.

    A refused trade still produced reasoning, so it still produces a verdict.
    Otherwise the halted days would be the only ones in the journal with no
    explanation, which is precisely backwards.
    """
    evidence = dict(rejection.evidence) or {"kind": rejection.kind}
    return Verdict(
        rule_id=f"risk:{rejection.kind.lower()}",
        principle=principle,
        passed=False,
        evidence=evidence,
        statement=rejection.statement,
    )


@dataclass
class RunResult:
    run_id: str
    decisions: list[Decision] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[date, Decimal]] = field(default_factory=list)
    halts: list[tuple[datetime, str, str]] = field(default_factory=list)
    rejections: list[tuple[datetime, Rejection]] = field(default_factory=list)
    bars_evaluated: int = 0
    starting_equity: Decimal = ZERO
    ending_equity: Decimal = ZERO

    @property
    def action_counts(self) -> dict[str, int]:
        counts = {a.value: 0 for a in Action}
        for decision in self.decisions:
            counts[decision.action.value] += 1
        return counts


class DecisionLoop:
    """Walks a bar sequence, deciding and recording."""

    def __init__(
        self,
        *,
        config: Config,
        bars: tuple[Bar, ...],
        gate: RiskGate,
        broker: SimulatedBroker,
        run_id: str,
        store: AuditStore | None = None,
        halt_resumes_next_session: bool = True,
    ) -> None:
        self.config = config
        self.bars = bars
        self.gate = gate
        self.broker = broker
        self.run_id = run_id
        self.store = store
        #: Backtest mode has no operator to press resume, so the halt lifts at
        #: the next session and the event is recorded. Paper mode passes False
        #: and requires `goldbot paper resume` (FR-014).
        self.halt_resumes_next_session = halt_resumes_next_session

        params = config.strategy
        self.entry_setup = EntrySetup(
            trend_lookback=params.trend_lookback,
            momentum_lookback=params.momentum_lookback,
            atr_lookback=params.atr_lookback,
            atr_multiple=params.atr_stop_multiple,
            reward_risk_target=params.reward_risk_target,
            blackout_dates=config.events.blackout_dates,
            event_policy=config.events.policy,
        )
        self.exit_setup = ExitSetup(lookback=params.momentum_lookback)

    def run(self) -> RunResult:
        cfg = self.config
        result = RunResult(run_id=self.run_id, starting_equity=cfg.initial_equity)

        cash: Decimal = cfg.initial_equity
        position: Position | None = None
        target: Decimal | None = None
        entry_fill: Fill | None = None
        pending_entry: Authorization | None = None
        pending_exit: bool = False

        session: date | None = None
        realised_today: Decimal = ZERO
        halted = False
        halt_reason = ""

        for index, bar in enumerate(self.bars):
            today = bar.end.date()

            if session is not None and today != session:
                # New session. In backtest mode the halt lifts here, which
                # stands in for the operator returning the following morning.
                realised_today = ZERO
                if halted and self.halt_resumes_next_session:
                    halted = False
                    halt_reason = ""
            session = today

            # --- 1. fill anything authorised yesterday, at today's open -----
            if pending_entry is not None:
                order, fill = self.broker.submit_entry(pending_entry, bar=bar, at=bar.start)
                cash -= fill.gross_value + fill.costs.total
                position = Position(
                    symbol=fill.symbol,
                    shares=fill.shares,
                    entry_price=fill.price,
                    stop=pending_entry.plan.stop,
                    opened_at=fill.at,
                    opening_decision_id=pending_entry.decision_id,
                    target=pending_entry.plan.target,
                    entry_costs=fill.costs.total,
                )
                target = pending_entry.plan.target
                entry_fill = fill
                if self.store is not None:
                    self.store.record_order(self.run_id, order)
                    self.store.record_fill(fill, fill.order_id)
                pending_entry = None

            # --- 2. did today take us out? ---------------------------------
            if position is not None and entry_fill is not None:
                signal = self.broker.check_exit(position, bar, target)
                exit_fill = None
                reason = None
                if signal is not None:
                    # A stop or target beats a pending rule exit: the market
                    # reached the level before the open order could act.
                    exit_fill = self.broker.submit_exit(
                        position,
                        price=signal.price,
                        shares=position.shares,
                        at=bar.start if signal.reason is ExitReason.GAP_THROUGH_STOP else bar.end,
                        decision_id=position.opening_decision_id,
                        intended=position.stop,
                    )
                    reason = signal.reason
                elif pending_exit:
                    exit_fill = self.broker.submit_exit(
                        position,
                        price=bar.open,
                        shares=position.shares,
                        at=bar.start,
                        decision_id=position.opening_decision_id,
                    )
                    reason = ExitReason.RULE

                if exit_fill is not None and reason is not None:
                    cash += exit_fill.gross_value - exit_fill.costs.total
                    realised_today += self._finalise(
                        result, position, entry_fill, exit_fill, reason
                    )
                    position, entry_fill, target = None, None, None
                pending_exit = False

            # --- daily loss halt -------------------------------------------
            equity = cash + (position.shares * bar.close if position else ZERO)
            if not halted and realised_today < ZERO and equity > ZERO:
                loss_fraction = -realised_today / cfg.initial_equity
                if loss_fraction >= cfg.envelope.max_daily_loss:
                    halted = True
                    halt_reason = (
                        f"Realised losses of {-realised_today:.2f} reached "
                        f"{loss_fraction:.2%} of starting equity, at or beyond the "
                        f"{cfg.envelope.max_daily_loss:.2%} daily limit."
                    )
                    result.halts.append((bar.end, "DAILY_LOSS", halt_reason))
                    if self.store is not None:
                        self.store.record_halt(self.run_id, bar.end, "DAILY_LOSS", halt_reason)

            # --- 3. what can be seen right now -----------------------------
            view = MarketView(self.bars[: index + 1], as_of=bar.end)
            result.bars_evaluated += 1

            # --- 4/5. decide, and authorise tomorrow -----------------------
            account = AccountState(
                equity=equity,
                cash=cash,
                session=today,
                realised_today=realised_today,
                positions=(position,) if position else (),
                halted=halted,
                halt_reason=halt_reason,
            )

            if position is not None:
                decision = self._decide_open(view, bar)
                if decision.action is Action.EXIT:
                    pending_exit = True
            else:
                decision, pending_entry = self._decide_flat(view, bar, account)

            result.decisions.append(decision)
            if self.store is not None:
                self.store.record_decision(self.run_id, decision)
            result.equity_curve.append((today, equity))

        # --- close anything still open at the end of the data --------------
        if position is not None and entry_fill is not None:
            last = self.bars[-1]
            exit_fill = self.broker.submit_exit(
                position,
                price=last.close,
                shares=position.shares,
                at=last.end,
                decision_id=position.opening_decision_id,
            )
            cash += exit_fill.gross_value - exit_fill.costs.total
            self._finalise(result, position, entry_fill, exit_fill, ExitReason.END_OF_DATA)

        result.ending_equity = cash
        return result

    def _finalise(
        self,
        result: RunResult,
        position: Position,
        entry_fill: Fill,
        exit_fill: Fill,
        reason: ExitReason,
    ) -> Decimal:
        """Close a trade, persist it, and return its realised result."""
        trade = self._close(position, entry_fill, exit_fill, reason)
        result.trades.append(trade)
        if self.store is not None:
            self.store.record_fill(exit_fill, exit_fill.order_id)
            self.store.record_trade(
                self.run_id,
                trade,
                trade_id=f"{self.run_id}:trade-{len(result.trades):04d}",
                entry_fill_id=entry_fill.order_id,
                exit_fill_id=exit_fill.order_id,
            )
        return trade.result_currency

    # -- decision helpers -------------------------------------------------

    def _decide_open(self, view: MarketView, bar: Bar) -> Decision:
        """In a position: does the reason for being here still hold?"""
        exit_result = self.exit_setup.evaluate(view)
        leaving = ExitSetup.should_exit(exit_result)
        decision = Decision(
            as_of=bar.end,
            symbol=self.config.symbol,
            action=Action.EXIT if leaving else Action.HOLD,
            verdicts=exit_result.verdicts,
            explanation="pending",
            run_id=self.run_id,
        )
        return self._with_explanation(decision)

    def _decide_flat(
        self, view: MarketView, bar: Bar, account: AccountState
    ) -> tuple[Decision, Authorization | None]:
        """Flat: is there a setup, can it be sized, and will the gate allow it?"""
        setup = self.entry_setup.evaluate(view)

        if not setup.all_passed or setup.stop is None:
            blocking = setup.blocking or setup.verdicts[0]
            return self._skip(bar, setup.verdicts, blocking), None

        sizing = size_position(
            entry=bar.close,
            stop=setup.stop,
            equity=account.equity,
            cash=account.cash,
            max_risk_per_trade=self.config.envelope.max_risk_per_trade,
        )
        if not sizing.is_tradable:
            blocking = Verdict(
                rule_id="risk:sizing",
                principle="position-sizing",
                passed=False,
                evidence={
                    "entry": bar.close,
                    "stop": setup.stop,
                    "equity": account.equity,
                    "cash": account.cash,
                },
                statement=f"No position could be sized: {sizing.reason}.",
            )
            return self._skip(bar, (*setup.verdicts, blocking), blocking), None

        plan = EntryPlan(
            intended_entry=bar.close,
            stop=setup.stop,
            shares=sizing.shares,
            risk_amount=sizing.risk_amount,
            risk_pct=sizing.risk_pct,
            binding_constraint=sizing.binding_constraint,
            target=setup.target,
        )
        candidate = Decision(
            as_of=bar.end,
            symbol=self.config.symbol,
            action=Action.ENTER,
            verdicts=setup.verdicts,
            explanation="pending",
            run_id=self.run_id,
            plan=plan,
        )

        outcome = self.gate.authorize(candidate, account, now=bar.end)
        if isinstance(outcome, Rejection):
            blocking = verdict_from_rejection(outcome, "capital-preservation")
            return self._skip(bar, (*setup.verdicts, blocking), blocking), None

        return self._with_explanation(candidate), outcome

    def _skip(
        self, bar: Bar, verdicts: tuple[Verdict, ...], blocking: Verdict
    ) -> Decision:
        decision = Decision(
            as_of=bar.end,
            symbol=self.config.symbol,
            action=Action.SKIP,
            verdicts=verdicts,
            explanation="pending",
            run_id=self.run_id,
            blocking_verdict=blocking,
        )
        return self._with_explanation(decision)

    @staticmethod
    def _with_explanation(decision: Decision) -> Decision:
        """Render the prose from the verdicts, then rebuild with it attached.

        The two-step exists because `Decision` refuses to be constructed without
        an explanation, and the explanation is derived from the decision. The
        placeholder never escapes this function.
        """
        from dataclasses import replace

        return replace(decision, explanation=explain(decision))

    def _close(
        self, position: Position, entry_fill: Fill, exit_fill: Fill, reason: ExitReason
    ) -> Trade:
        trade = Trade(
            symbol=position.symbol,
            entry_fill=entry_fill,
            exit_fill=exit_fill,
            shares=position.shares,
            exit_reason=reason,
            planned_risk=position.initial_risk,
            opening_decision_id=position.opening_decision_id,
            closing_decision_id=exit_fill.decision_id,
        )
        classification = LossClass.CORRECT if not trade.is_win else None
        from dataclasses import replace

        return replace(trade, classification=classification)
