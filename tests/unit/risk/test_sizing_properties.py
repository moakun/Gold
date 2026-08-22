"""Properties that must hold for every sizing input, not just the ones I thought of.

The per-trade risk limit is the single most important invariant in the system.
Example-based tests check the cases an author imagined; these check the cases
they did not.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from goldbot.domain.decision import Constraint
from goldbot.domain.money import dec
from goldbot.risk.sizing import size_position

# Cents-precision decimals built from integers, never floats.
cents = st.integers(min_value=1, max_value=100_000_00).map(lambda n: Decimal(n) / 100)
equities = st.integers(min_value=100_00, max_value=10_000_000_00).map(lambda n: Decimal(n) / 100)
risk_limits = st.sampled_from([dec("0.0025"), dec("0.005"), dec("0.010"), dec("0.020")])


@settings(max_examples=300, deadline=None)
@given(entry=cents, gap=cents, equity=equities, limit=risk_limits)
def test_risk_never_exceeds_the_limit(
    entry: Decimal, gap: Decimal, equity: Decimal, limit: Decimal
) -> None:
    """The invariant Principle I rests on."""
    stop = entry - gap
    if stop <= 0:
        return
    result = size_position(
        entry=entry, stop=stop, equity=equity, cash=equity, max_risk_per_trade=limit
    )
    if result.is_tradable:
        assert result.risk_pct <= limit, (
            f"{result.shares} shares at {entry} with stop {stop} risks "
            f"{result.risk_pct} against a limit of {limit}"
        )


@settings(max_examples=300, deadline=None)
@given(entry=cents, gap=cents, equity=equities, cash=equities, limit=risk_limits)
def test_position_never_costs_more_than_available_cash(
    entry: Decimal, gap: Decimal, equity: Decimal, cash: Decimal, limit: Decimal
) -> None:
    stop = entry - gap
    if stop <= 0:
        return
    result = size_position(
        entry=entry, stop=stop, equity=equity, cash=cash, max_risk_per_trade=limit
    )
    if result.is_tradable:
        assert result.shares * entry <= cash


@settings(max_examples=200, deadline=None)
@given(entry=cents, gap=cents, equity=equities, limit=risk_limits)
def test_shares_are_whole_and_non_negative(
    entry: Decimal, gap: Decimal, equity: Decimal, limit: Decimal
) -> None:
    stop = entry - gap
    if stop <= 0:
        return
    result = size_position(
        entry=entry, stop=stop, equity=equity, cash=equity, max_risk_per_trade=limit
    )
    assert isinstance(result.shares, int)
    assert result.shares >= 0


@settings(max_examples=200, deadline=None)
@given(entry=cents, gap=cents, equity=equities, limit=risk_limits)
def test_an_untradable_size_always_explains_itself(
    entry: Decimal, gap: Decimal, equity: Decimal, limit: Decimal
) -> None:
    """Zero shares is an ordinary outcome, but it may never be a silent one."""
    stop = entry - gap
    if stop <= 0:
        return
    result = size_position(
        entry=entry, stop=stop, equity=equity, cash=equity, max_risk_per_trade=limit
    )
    if not result.is_tradable:
        assert result.reason, "a zero-share result must say why"
        assert result.binding_constraint in (Constraint.RISK_BUDGET, Constraint.AVAILABLE_CASH)


@settings(max_examples=200, deadline=None)
@given(entry=cents, gap=cents, equity=equities, limit=risk_limits)
def test_a_wider_stop_never_increases_size(
    entry: Decimal, gap: Decimal, equity: Decimal, limit: Decimal
) -> None:
    """More risk per share must mean fewer shares. Monotonicity, in other words."""
    stop = entry - gap
    wider = entry - gap * 2
    if stop <= 0 or wider <= 0:
        return
    tight = size_position(
        entry=entry, stop=stop, equity=equity, cash=equity, max_risk_per_trade=limit
    )
    loose = size_position(
        entry=entry, stop=wider, equity=equity, cash=equity, max_risk_per_trade=limit
    )
    assert loose.shares <= tight.shares
