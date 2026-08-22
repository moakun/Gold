"""The fill model, especially the case the fixture data does not reach.

Gapping through a stop is the defining risk of holding an instrument that is
shut most of the day, so it gets crafted bars rather than waiting for history
to produce one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from goldbot.domain.instrument import Instrument
from goldbot.domain.money import ZERO, dec
from goldbot.domain.order import Fill, Side
from goldbot.domain.position import ExitReason, Position, Trade
from goldbot.execution.simulated import SimulatedBroker
from tests.conftest import make_bar

NOW = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)


@pytest.fixture
def broker(gld: Instrument) -> SimulatedBroker:
    return SimulatedBroker(gld, run_id="test")


@pytest.fixture
def position() -> Position:
    return Position(
        symbol="GLD",
        shares=100,
        entry_price=dec("200.00"),
        stop=dec("196.00"),
        opened_at=NOW,
        opening_decision_id="d1",
        target=dec("208.00"),
    )


def test_a_quiet_bar_does_not_exit(broker: SimulatedBroker, position: Position) -> None:
    bar = make_bar(NOW, open_="200.50", high="202.00", low="199.00", close="201.00")
    assert broker.check_exit(position, bar, position.target) is None


def test_touching_the_stop_intrabar_fills_at_the_stop(
    broker: SimulatedBroker, position: Position
) -> None:
    bar = make_bar(NOW, open_="199.00", high="199.50", low="195.50", close="197.00")
    signal = broker.check_exit(position, bar, position.target)
    assert signal is not None
    assert signal.reason is ExitReason.STOP
    assert signal.price == dec("196.00")


def test_a_gap_below_the_stop_fills_at_the_open(
    broker: SimulatedBroker, position: Position
) -> None:
    """The honest case. The stop was 196; the market reopened at 188."""
    bar = make_bar(NOW, open_="188.00", high="189.00", low="186.00", close="187.00")
    signal = broker.check_exit(position, bar, position.target)
    assert signal is not None
    assert signal.reason is ExitReason.GAP_THROUGH_STOP
    assert signal.price == dec("188.00"), "filling at the stop here would be a lie"


def test_the_stop_wins_when_a_bar_covers_both_levels(
    broker: SimulatedBroker, position: Position
) -> None:
    """Daily bars cannot say which came first; assuming the good outcome inflates results."""
    bar = make_bar(NOW, open_="200.00", high="209.00", low="195.00", close="205.00")
    signal = broker.check_exit(position, bar, position.target)
    assert signal is not None
    assert signal.reason is ExitReason.STOP


def test_reaching_the_target_exits_at_the_target(
    broker: SimulatedBroker, position: Position
) -> None:
    bar = make_bar(NOW, open_="203.00", high="209.00", low="202.50", close="208.50")
    signal = broker.check_exit(position, bar, position.target)
    assert signal is not None
    assert signal.reason is ExitReason.TARGET
    assert signal.price == dec("208.00")


def test_a_gap_loss_is_recorded_as_a_risk_overrun(
    broker: SimulatedBroker, position: Position
) -> None:
    """The number that keeps "the 1% rule held" a measurement, not an assumption."""
    entry = Fill(
        order_id="o1",
        decision_id="d1",
        symbol="GLD",
        side=Side.BUY,
        price=dec("200.00"),
        shares=100,
        at=NOW,
        costs=broker._costs(dec("200.00"), 100),
    )
    exit_fill = broker.submit_exit(
        position,
        price=dec("188.00"),
        shares=100,
        at=NOW + timedelta(days=1),
        decision_id="d1",
        intended=position.stop,
    )
    trade = Trade(
        symbol="GLD",
        entry_fill=entry,
        exit_fill=exit_fill,
        shares=100,
        exit_reason=ExitReason.GAP_THROUGH_STOP,
        planned_risk=position.initial_risk,
        opening_decision_id="d1",
        closing_decision_id="d1",
    )

    assert trade.planned_risk == dec("400.00")
    assert trade.result_currency < -dec("400.00")
    assert trade.risk_overrun > ZERO
    assert exit_fill.slippage_vs_intended == dec("-8.00")


def test_a_loss_inside_the_plan_reports_no_overrun(broker: SimulatedBroker) -> None:
    position = Position(
        symbol="GLD",
        shares=10,
        entry_price=dec("200.00"),
        stop=dec("196.00"),
        opened_at=NOW,
        opening_decision_id="d1",
    )
    entry = Fill(
        order_id="o1",
        decision_id="d1",
        symbol="GLD",
        side=Side.BUY,
        price=dec("200.00"),
        shares=10,
        at=NOW,
        costs=broker._costs(dec("200.00"), 10),
    )
    exit_fill = broker.submit_exit(
        position, price=dec("198.00"), shares=10, at=NOW, decision_id="d1"
    )
    trade = Trade(
        symbol="GLD",
        entry_fill=entry,
        exit_fill=exit_fill,
        shares=10,
        exit_reason=ExitReason.RULE,
        planned_risk=position.initial_risk,
        opening_decision_id="d1",
        closing_decision_id="d1",
    )
    assert trade.risk_overrun == ZERO


def test_the_broker_refuses_anything_that_is_not_an_authorization(
    broker: SimulatedBroker,
) -> None:
    bar = make_bar(NOW)
    with pytest.raises(TypeError, match="Authorization"):
        broker.submit_entry("not an authorization", bar=bar, at=NOW)  # type: ignore[arg-type]
