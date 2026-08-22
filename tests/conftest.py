"""Shared builders for the test suite.

Deliberately explicit rather than clever: a test that fails should point at a
requirement, not at a fixture factory.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from goldbot.domain.account import AccountState
from goldbot.domain.bar import Bar, MarketView
from goldbot.domain.decision import Action, Constraint, Decision, EntryPlan
from goldbot.domain.envelope import RiskEnvelope
from goldbot.domain.instrument import AllowList, Instrument
from goldbot.domain.money import dec
from goldbot.domain.verdict import Verdict

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def gld() -> Instrument:
    return Instrument(symbol="GLD", name="Test Gold ETF", expense_ratio=dec("0.0040"))


@pytest.fixture
def allow_list(gld: Instrument) -> AllowList:
    return AllowList((gld,))


@pytest.fixture
def envelope() -> RiskEnvelope:
    return RiskEnvelope()


def make_bar(
    end: datetime,
    *,
    symbol: str = "GLD",
    open_: str = "200.00",
    high: str = "202.00",
    low: str = "199.00",
    close: str = "201.00",
    volume: int = 1_000_000,
) -> Bar:
    return Bar(
        symbol=symbol,
        start=end - timedelta(hours=6, minutes=30),
        end=end,
        open=dec(open_),
        high=dec(high),
        low=dec(low),
        close=dec(close),
        volume=volume,
    )


def make_bars(count: int, symbol: str = "GLD") -> tuple[Bar, ...]:
    base = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)
    return tuple(make_bar(base + timedelta(days=i), symbol=symbol) for i in range(count))


def make_view(count: int = 30, symbol: str = "GLD") -> MarketView:
    bars = make_bars(count, symbol)
    return MarketView(bars, as_of=bars[-1].end)


def make_verdict(
    *,
    rule_id: str = "test_rule",
    principle: str = "trend-alignment",
    passed: bool = True,
    statement: str = "Close 201.00 is above its 20-day average 198.00",
) -> Verdict:
    return Verdict(
        rule_id=rule_id,
        principle=principle,
        passed=passed,
        evidence={"close": dec("201.00"), "sma_20": dec("198.00")},
        statement=statement,
    )


def make_plan(
    *,
    entry: str = "200.00",
    stop: str = "196.00",
    shares: int = 25,
    risk_pct: str = "0.010",
    target: str | None = "212.00",
    constraint: Constraint = Constraint.RISK_BUDGET,
) -> EntryPlan:
    entry_d, stop_d = dec(entry), dec(stop)
    return EntryPlan(
        intended_entry=entry_d,
        stop=stop_d,
        shares=shares,
        risk_amount=(entry_d - stop_d) * shares,
        risk_pct=dec(risk_pct),
        binding_constraint=constraint,
        target=dec(target) if target else None,
    )


def make_decision(
    *,
    action: Action = Action.ENTER,
    plan: EntryPlan | None = None,
    symbol: str = "GLD",
    as_of: datetime | None = None,
    run_id: str = "test-run",
    verdicts: tuple[Verdict, ...] | None = None,
    blocking: Verdict | None = None,
) -> Decision:
    if plan is None and action is Action.ENTER:
        plan = make_plan()
    return Decision(
        as_of=as_of or datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
        symbol=symbol,
        action=action,
        verdicts=verdicts or (make_verdict(),),
        explanation="Test decision explanation.",
        run_id=run_id,
        plan=plan,
        blocking_verdict=blocking,
    )


def make_account(
    *,
    equity: str = "100000.00",
    cash: str | None = None,
    realised_today: str = "0.00",
    positions: tuple = (),
    halted: bool = False,
    session: date | None = None,
) -> AccountState:
    equity_d: Decimal = dec(equity)
    return AccountState(
        equity=equity_d,
        cash=dec(cash) if cash is not None else equity_d,
        session=session or date(2026, 1, 5),
        realised_today=dec(realised_today),
        positions=positions,
        halted=halted,
    )
