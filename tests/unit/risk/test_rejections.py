"""Every way the risk gate must say no.

Written before the guards they cover, per the constitution's development
workflow. A risk control that has never been observed refusing anything is a
risk control nobody has tested.

The forbidden operations of Principle I — widening a stop, removing a stop,
averaging down — are covered here too, though they are enforced by the absence
of the operation rather than by a runtime check. The tests assert that absence.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from goldbot.domain.account import AccountState
from goldbot.domain.decision import Action, Constraint, EntryPlan
from goldbot.domain.errors import GuardViolation
from goldbot.domain.instrument import AllowList, Instrument
from goldbot.domain.money import dec
from goldbot.domain.order import Authorization
from goldbot.domain.position import Position
from goldbot.domain.verdict import Rejection
from goldbot.risk.gate import RiskGate
from tests.conftest import make_account, make_decision, make_plan

NOW = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)


@pytest.fixture
def gate(allow_list: AllowList, envelope) -> RiskGate:  # type: ignore[no-untyped-def]
    return RiskGate(allow_list=allow_list, envelope=envelope)


def test_the_happy_path_yields_an_authorization(gate: RiskGate) -> None:
    """Establishes the baseline the rejections deviate from."""
    result = gate.authorize(make_decision(), make_account(), now=NOW)
    assert isinstance(result, Authorization)
    assert result.envelope_version == gate.envelope.version


# ---------------------------------------------------------------------------
# Principle II — gold only, failing closed
# ---------------------------------------------------------------------------


def test_a_symbol_off_the_allow_list_is_refused(gate: RiskGate) -> None:
    result = gate.authorize(make_decision(symbol="SPY"), make_account(), now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "ALLOW_LIST"
    assert "SPY" in result.statement


def test_the_allow_list_itself_fails_closed(allow_list: AllowList) -> None:
    with pytest.raises(GuardViolation):
        allow_list.require("SLV")


def test_a_correlated_market_is_readable_but_not_tradable(gate: RiskGate) -> None:
    """DXY may inform a decision; it may never be the thing we buy."""
    result = gate.authorize(make_decision(symbol="DXY"), make_account(), now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "ALLOW_LIST"


# ---------------------------------------------------------------------------
# Principle I — capital preservation
# ---------------------------------------------------------------------------


def test_risk_above_the_per_trade_limit_is_refused(gate: RiskGate) -> None:
    over = make_plan(risk_pct="0.025")  # envelope allows 1.0%
    result = gate.authorize(make_decision(plan=over), make_account(), now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "RISK_EXCEEDED"
    assert "2.5" in result.statement or "0.025" in result.statement


def test_an_entry_without_a_stop_cannot_even_be_described() -> None:
    """There is no way to express a stopless entry, which is the point."""
    with pytest.raises(ValueError, match="stop"):
        EntryPlan(
            intended_entry=dec("200.00"),
            stop=dec("204.00"),  # above entry: not a stop
            shares=10,
            risk_amount=dec("-40.00"),
            risk_pct=dec("0.004"),
            binding_constraint=Constraint.RISK_BUDGET,
        )


def test_a_plan_whose_arithmetic_does_not_add_up_is_refused() -> None:
    with pytest.raises(ValueError, match="internally inconsistent"):
        EntryPlan(
            intended_entry=dec("200.00"),
            stop=dec("196.00"),
            shares=25,
            risk_amount=dec("10.00"),  # should be 100.00
            risk_pct=dec("0.001"),
            binding_constraint=Constraint.RISK_BUDGET,
        )


def test_widening_a_stop_is_refused() -> None:
    position = Position(
        symbol="GLD",
        shares=25,
        entry_price=dec("200.00"),
        stop=dec("196.00"),
        opened_at=NOW,
        opening_decision_id="abc",
    )
    with pytest.raises(GuardViolation, match="tightened"):
        position.tighten_stop(dec("190.00"))


def test_tightening_a_stop_is_allowed() -> None:
    position = Position(
        symbol="GLD",
        shares=25,
        entry_price=dec("200.00"),
        stop=dec("196.00"),
        opened_at=NOW,
        opening_decision_id="abc",
    )
    tightened = position.tighten_stop(dec("198.00"))
    assert tightened.stop == dec("198.00")
    assert position.stop == dec("196.00"), "the original must be untouched"


def test_there_is_no_api_for_averaging_down() -> None:
    position = Position(
        symbol="GLD",
        shares=25,
        entry_price=dec("200.00"),
        stop=dec("196.00"),
        opened_at=NOW,
        opening_decision_id="abc",
    )
    for forbidden in ("add_shares", "average_down", "scale_in", "widen_stop", "remove_stop"):
        assert not hasattr(position, forbidden), (
            f"Position exposes {forbidden}; Principle I forbids that operation, so it should "
            "not exist rather than be blocked at runtime"
        )


def test_a_second_position_is_refused_at_the_concurrency_limit(gate: RiskGate) -> None:
    open_position = Position(
        symbol="GLD",
        shares=10,
        entry_price=dec("200.00"),
        stop=dec("196.00"),
        opened_at=NOW,
        opening_decision_id="abc",
    )
    account = make_account(positions=(open_position,))
    result = gate.authorize(make_decision(), account, now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "POSITION_LIMIT"


def test_an_entry_costing_more_than_available_cash_is_refused(gate: RiskGate) -> None:
    account = make_account(equity="100000.00", cash="1000.00")
    result = gate.authorize(make_decision(), account, now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "INSUFFICIENT_CASH"


# ---------------------------------------------------------------------------
# Halts
# ---------------------------------------------------------------------------


def test_the_daily_loss_halt_blocks_new_entries(gate: RiskGate) -> None:
    account = make_account(equity="100000.00", realised_today="-3500.00")  # -3.5% vs 3% limit
    result = gate.authorize(make_decision(), account, now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "DAILY_LOSS_HALT"


def test_a_loss_below_the_limit_does_not_halt(gate: RiskGate) -> None:
    account = make_account(equity="100000.00", realised_today="-1200.00")  # -1.2%
    assert isinstance(gate.authorize(make_decision(), account, now=NOW), Authorization)


def test_an_already_halted_account_is_refused(gate: RiskGate) -> None:
    result = gate.authorize(make_decision(), make_account(halted=True), now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "HALTED"


def test_the_kill_switch_latch_refuses_everything(gate: RiskGate, tmp_path) -> None:  # type: ignore[no-untyped-def]
    latch = tmp_path / "kill.latch"
    latch.write_text("engaged", encoding="utf-8")
    latched = RiskGate(allow_list=gate.allow_list, envelope=gate.envelope, kill_latch=latch)
    result = latched.authorize(make_decision(), make_account(), now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "KILL_SWITCH"


# ---------------------------------------------------------------------------
# Shape of a refusal
# ---------------------------------------------------------------------------


def test_a_non_entry_decision_is_not_authorizable(gate: RiskGate) -> None:
    result = gate.authorize(make_decision(action=Action.HOLD, plan=None), make_account(), now=NOW)
    assert isinstance(result, Rejection)
    assert result.kind == "NOT_AN_ENTRY"


def test_every_rejection_explains_itself_in_words(gate: RiskGate) -> None:
    """A refused trade is a teaching moment, not an error code."""
    cases: list[tuple[str, AccountState]] = [
        ("SPY", make_account()),
        ("GLD", make_account(halted=True)),
        ("GLD", make_account(equity="100000.00", realised_today="-9000.00")),
        ("GLD", make_account(equity="100000.00", cash="10.00")),
    ]
    for symbol, account in cases:
        result = gate.authorize(make_decision(symbol=symbol), account, now=NOW)
        assert isinstance(result, Rejection)
        assert len(result.statement.split()) >= 6, f"terse rejection: {result.statement!r}"
        assert result.kind.isupper()
