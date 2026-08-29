"""The kill switch, and the latch that keeps it killed.

Written before the implementation. The requirements are specific: it must
flatten and cancel, it must latch, it must be idempotent, and nothing except an
explicit clear may release it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from goldbot.domain.envelope import RiskEnvelope
from goldbot.domain.instrument import AllowList, Instrument
from goldbot.domain.verdict import Rejection
from goldbot.risk.gate import RiskGate
from goldbot.risk.kill_switch import KillSwitch
from tests.conftest import make_account, make_decision

NOW = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)


@pytest.fixture
def switch(tmp_path: Path) -> KillSwitch:
    return KillSwitch(tmp_path / "kill.latch")


def test_a_fresh_switch_is_not_engaged(switch: KillSwitch) -> None:
    assert switch.engaged is False


def test_engaging_sets_the_latch(switch: KillSwitch) -> None:
    result = switch.engage(at=NOW, cancel=2, flatten=1, note="operator pulled the cord")
    assert switch.engaged
    assert result.orders_cancelled == 2
    assert result.positions_flattened == 1
    assert "operator pulled the cord" in switch.reason()


def test_engaging_twice_is_idempotent(switch: KillSwitch) -> None:
    switch.engage(at=NOW)
    second = switch.engage(at=NOW)
    assert second.already_engaged is True
    assert switch.engaged


def test_it_is_safe_to_engage_with_nothing_open(switch: KillSwitch) -> None:
    result = switch.engage(at=NOW, cancel=0, flatten=0)
    assert result.orders_cancelled == 0
    assert switch.engaged


def test_only_an_explicit_clear_releases_it(switch: KillSwitch) -> None:
    switch.engage(at=NOW)
    assert switch.clear() is True
    assert switch.engaged is False
    assert switch.clear() is False, "clearing an unengaged switch reports that it was not set"


def test_the_latch_survives_the_process(tmp_path: Path) -> None:
    """A file, not a variable — a crash must not un-stop a stopped system."""
    KillSwitch(tmp_path / "kill.latch").engage(at=NOW)
    assert KillSwitch(tmp_path / "kill.latch").engaged


def test_an_engaged_latch_makes_the_gate_refuse_everything(tmp_path: Path) -> None:
    latch = tmp_path / "kill.latch"
    KillSwitch(latch).engage(at=NOW)

    gate = RiskGate(
        allow_list=AllowList((Instrument(symbol="GLD", name="Test Gold ETF"),)),
        envelope=RiskEnvelope(),
        kill_latch=latch,
    )
    outcome = gate.authorize(make_decision(), make_account(), now=NOW)
    assert isinstance(outcome, Rejection)
    assert outcome.kind == "KILL_SWITCH"


def test_it_completes_well_inside_the_ten_second_budget(switch: KillSwitch) -> None:
    """SC-008. Generous by design — the point is that it is not slow."""
    result = switch.engage(at=NOW, cancel=5, flatten=1)
    assert result.elapsed_seconds < 10.0
