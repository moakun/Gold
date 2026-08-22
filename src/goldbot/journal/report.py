"""Performance, reported honestly or not at all.

FR-026 requires the full metric set together. The enforcement here is that the
only rendering methods emit everything — there is no `format_win_rate()` a
caller could reach for when the other numbers are less flattering. The fields
exist on the metrics object because tests and the CLI need them; what does not
exist is a supported way to *present* one alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from goldbot.domain.money import ZERO, dec
from goldbot.domain.position import ExitReason, LossClass, Trade


@dataclass(frozen=True, slots=True)
class Metrics:
    trade_count: int
    wins: int
    losses: int
    win_rate: Decimal
    expectancy_r: Decimal
    average_win_r: Decimal
    average_loss_r: Decimal
    max_drawdown_pct: Decimal
    total_return: Decimal
    total_return_pct: Decimal
    total_costs: Decimal
    gross_before_costs: Decimal
    risk_overrun_count: int
    risk_overrun_total: Decimal
    gap_exits: int
    stop_exits: int
    target_exits: int
    rule_exits: int
    correct_losses: int
    rule_violation_losses: int
    system_error_losses: int
    expense_ratio: Decimal
    starting_equity: Decimal
    ending_equity: Decimal


def max_drawdown(curve: list[tuple[date, Decimal]]) -> Decimal:
    """Largest peak-to-trough decline as a fraction of the peak."""
    if not curve:
        return ZERO
    peak = curve[0][1]
    worst = ZERO
    for _, equity in curve:
        peak = max(peak, equity)
        if peak > ZERO:
            drop = (peak - equity) / peak
            worst = max(worst, drop)
    return worst


def compute(
    *,
    trades: list[Trade],
    equity_curve: list[tuple[date, Decimal]],
    starting_equity: Decimal,
    ending_equity: Decimal,
    expense_ratio: Decimal,
) -> Metrics:
    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]
    count = len(trades)

    win_rate = dec(len(wins)) / count if count else ZERO
    expectancy = sum((t.result_r for t in trades), ZERO) / count if count else ZERO
    avg_win = sum((t.result_r for t in wins), ZERO) / len(wins) if wins else ZERO
    avg_loss = sum((t.result_r for t in losses), ZERO) / len(losses) if losses else ZERO

    overruns = [t for t in trades if t.risk_overrun > ZERO]
    total_costs = sum((t.total_costs for t in trades), ZERO)
    gross = sum((t.gross_result for t in trades), ZERO)
    net = ending_equity - starting_equity

    return Metrics(
        trade_count=count,
        wins=len(wins),
        losses=len(losses),
        win_rate=win_rate,
        expectancy_r=expectancy,
        average_win_r=avg_win,
        average_loss_r=avg_loss,
        max_drawdown_pct=max_drawdown(equity_curve),
        total_return=net,
        total_return_pct=(net / starting_equity) if starting_equity > ZERO else ZERO,
        total_costs=total_costs,
        gross_before_costs=gross,
        risk_overrun_count=len(overruns),
        risk_overrun_total=sum((t.risk_overrun for t in overruns), ZERO),
        gap_exits=sum(1 for t in trades if t.exit_reason is ExitReason.GAP_THROUGH_STOP),
        stop_exits=sum(1 for t in trades if t.exit_reason is ExitReason.STOP),
        target_exits=sum(1 for t in trades if t.exit_reason is ExitReason.TARGET),
        rule_exits=sum(1 for t in trades if t.exit_reason is ExitReason.RULE),
        correct_losses=sum(1 for t in losses if t.classification is LossClass.CORRECT),
        rule_violation_losses=sum(
            1 for t in losses if t.classification is LossClass.RULE_VIOLATION
        ),
        system_error_losses=sum(1 for t in losses if t.classification is LossClass.SYSTEM_ERROR),
        expense_ratio=expense_ratio,
        starting_equity=starting_equity,
        ending_equity=ending_equity,
    )


def render(metrics: Metrics, *, cadence: str = "daily") -> str:
    """The whole set, every time.

    No caller gets a version of this with the awkward lines removed.
    """
    m = metrics
    lines = [
        "PERFORMANCE",
        "=" * 68,
        f"  Trades              {m.trade_count}",
        f"  Win rate            {m.win_rate:.1%}  ({m.wins} won, {m.losses} lost)",
        f"  Expectancy          {m.expectancy_r:+.3f} R per trade",
        f"  Average win         {m.average_win_r:+.2f} R",
        f"  Average loss        {m.average_loss_r:+.2f} R",
        f"  Max drawdown        {m.max_drawdown_pct:.2%}",
        f"  Return (net)        {m.total_return:+,.2f}  ({m.total_return_pct:+.2%})",
        "",
        "COSTS",
        "-" * 68,
        f"  Gross before costs  {m.gross_before_costs:+,.2f}",
        f"  Total costs         {m.total_costs:,.2f}  (spread, slippage, commission)",
        f"  Fund expense ratio  {m.expense_ratio:.2%} per year — disclosed, not charged.",
        "                      It is already inside the ETF's own price series,",
        "                      which is the series traded. Charging it again would",
        "                      count it twice.",
        "",
        "HOW TRADES ENDED",
        "-" * 68,
        f"  Stop                {m.stop_exits}",
        f"  Gap through stop    {m.gap_exits}",
        f"  Target              {m.target_exits}",
        f"  Exit rule           {m.rule_exits}",
        "",
        "DID THE RISK LIMIT ACTUALLY HOLD?",
        "-" * 68,
        f"  Trades over plan    {m.risk_overrun_count}",
        f"  Excess loss         {m.risk_overrun_total:,.2f}",
    ]

    if m.risk_overrun_count == 0 and m.trade_count > 20:
        lines.append(
            "  Note: zero overruns across this many trades usually means the fill\n"
            "        model is assuming stops always execute at their price. For an\n"
            "        instrument closed most of the day, treat that with suspicion."
        )
    else:
        lines.append(
            "  A stop is an intention, not a guarantee. These are the trades where\n"
            "  the market reopened beyond it and the loss exceeded the plan."
        )

    lines += [
        "",
        "LOSSES, CLASSIFIED",
        "-" * 68,
        f"  Correctly taken     {m.correct_losses}",
        f"  Rule violations     {m.rule_violation_losses}",
        f"  System errors       {m.system_error_losses}",
    ]
    if m.rule_violation_losses or m.system_error_losses:
        lines.append(
            "  The bottom two rows are the important ones: those losses were not the\n"
            "  cost of doing business, they were process failures."
        )

    if cadence == "4h":
        lines += [
            "",
            "DATA CAVEAT",
            "-" * 68,
            "  4-hour mode uses IEX-sourced intraday prints, a minority of consolidated",
            "  volume. Intraday prices can deviate from the consolidated tape.",
        ]

    return "\n".join(lines)
