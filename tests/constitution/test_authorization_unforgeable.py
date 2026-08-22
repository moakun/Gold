"""Principle I: the risk gate is the only way to reach the broker.

`Authorization` is a capability token. The chain is:

    verdicts -> Decision -> RiskGate.authorize -> Authorization -> Broker

Every link refuses to skip a step. This is a guard rather than a security
boundary — Python cannot stop a determined caller from importing a private
name — but it makes the correct path the only obvious one, and it makes the
incorrect path fail here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from goldbot.domain.decision import Constraint, EntryPlan
from goldbot.domain.errors import GuardViolation
from goldbot.domain.money import dec
from goldbot.domain.order import Authorization, Side
from tests.constitution._scan import imported_names, modules_in, rel

pytestmark = pytest.mark.constitution

PLAN = EntryPlan(
    intended_entry=dec("200.00"),
    stop=dec("196.00"),
    shares=25,
    risk_amount=dec("100.00"),
    risk_pct=dec("0.001"),
    binding_constraint=Constraint.RISK_BUDGET,
)


def test_direct_construction_is_refused() -> None:
    with pytest.raises(GuardViolation, match="RiskGate"):
        Authorization(
            decision_id="forged",
            symbol="GLD",
            side=Side.BUY,
            plan=PLAN,
            issued_at=datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
            envelope_version="deadbeef",
        )


def test_passing_a_guessed_token_is_refused() -> None:
    with pytest.raises(GuardViolation):
        Authorization(
            decision_id="forged",
            symbol="GLD",
            side=Side.BUY,
            plan=PLAN,
            issued_at=datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
            envelope_version="deadbeef",
            _token=object(),
        )


def test_only_the_risk_gate_imports_the_mint() -> None:
    """If a second module learns to mint authorizations, the guarantee is gone."""
    importers = [
        rel(path)
        for package in ("domain", "data", "strategy", "risk", "execution", "engine", "journal", "lessons", "cli")
        for path in modules_in(package)
        if any("_mint_authorization" in name for name in imported_names(path))
    ]
    assert importers == ["src/goldbot/risk/gate.py"], (
        f"_mint_authorization is imported by {importers}; only the risk gate may mint "
        "authorizations, or Principle I has a second door"
    )


def test_a_gate_issued_authorization_is_accepted() -> None:
    """The positive case, so the test above cannot pass by nothing working."""
    from goldbot.domain.envelope import RiskEnvelope
    from goldbot.domain.instrument import AllowList, Instrument
    from goldbot.risk.gate import RiskGate
    from tests.conftest import make_account, make_decision

    gate = RiskGate(
        allow_list=AllowList((Instrument(symbol="GLD", name="Test Gold ETF"),)),
        envelope=RiskEnvelope(),
    )
    result = gate.authorize(
        make_decision(), make_account(), now=datetime(2026, 1, 5, 21, 0, tzinfo=UTC)
    )
    assert isinstance(result, Authorization)
