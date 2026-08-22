"""FR-021: frictionless results are not results.

Every fill carries spread, slippage, and commission, itemised rather than
rolled into one number — so a report can answer "where did the edge go?"
rather than just showing a smaller figure.

The expense ratio is deliberately absent from the cost total. It is already
inside the ETF's price series (research.md R10); charging it again would
understate every result by roughly the fee per year held.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from goldbot.domain.money import ZERO
from tests.integration._helpers import run_backtest


def test_every_fill_costs_something(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    assert artifacts.result.trades, "the fixture should produce trades"
    for trade in artifacts.result.trades:
        assert trade.entry_fill.costs.total > ZERO
        assert trade.exit_fill.costs.total > ZERO


def test_costs_are_itemised(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    costs = artifacts.result.trades[0].entry_fill.costs
    assert costs.spread > ZERO
    assert costs.slippage > ZERO
    assert costs.total == costs.spread + costs.slippage + costs.commission


def test_net_result_is_below_gross(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    metrics = artifacts.metrics
    assert metrics.total_costs > ZERO
    assert metrics.total_return < metrics.gross_before_costs


def test_the_report_states_every_metric(tmp_path: Path) -> None:
    """FR-026: no caller gets a version with the awkward lines removed."""
    artifacts, _ = run_backtest(tmp_path)
    text = artifacts.report_path.read_text(encoding="utf-8")
    for required in (
        "Trades",
        "Win rate",
        "Expectancy",
        "Max drawdown",
        "Return (net)",
        "Total costs",
        "Fund expense ratio",
        "Trades over plan",
        "LOSSES, CLASSIFIED",
    ):
        assert required in text, f"report omits {required!r}"


def test_the_expense_ratio_is_disclosed_but_not_charged(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    text = artifacts.report_path.read_text(encoding="utf-8")
    assert "disclosed, not charged" in text

    # Costs must come only from spread, slippage, and commission.
    from_fills: Decimal = sum(
        (t.entry_fill.costs.total + t.exit_fill.costs.total for t in artifacts.result.trades),
        ZERO,
    )
    assert artifacts.metrics.total_costs == from_fills


def test_slippage_against_the_trigger_price_is_recorded(tmp_path: Path) -> None:
    """FR-038: a decision made after the close never fills at the closing price."""
    artifacts, _ = run_backtest(tmp_path)
    entries = [t.entry_fill for t in artifacts.result.trades]
    assert any(f.slippage_vs_intended != ZERO for f in entries), (
        "every entry filled at exactly its trigger price, which cannot be right for a "
        "next-open execution model"
    )
