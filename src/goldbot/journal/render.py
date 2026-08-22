"""Rendering the journal.

Two audiences. The Markdown file is for reading later — what happened on the
14th of March and why. The Rich console output is for watching a session unfold.
Both are derived from the same decisions, so neither can tell a different story.
"""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from goldbot.domain.decision import Action, Decision
from goldbot.domain.position import Trade
from goldbot.journal.explain import explain, one_line

ACTION_STYLE = {
    Action.ENTER: "bold green",
    Action.EXIT: "bold yellow",
    Action.HOLD: "dim",
    Action.SKIP: "dim cyan",
}


def markdown_journal(
    *,
    fingerprint: str,
    symbol: str,
    decisions: list[Decision],
    trades: list[Trade],
    snapshot_id: str,
    config_version: str,
    include_holds: bool = True,
) -> str:
    """The full decision journal.

    Every evaluated bar appears, including the ones where nothing happened.
    That is the whole point of FR-001: the days the system declined to trade
    are days it made a decision, and a journal that only records trades teaches
    you nothing about the other ninety percent of the time.
    """
    counts = {a.value: 0 for a in Action}
    for decision in decisions:
        counts[decision.action.value] += 1

    # The header carries the reproducibility triple's fingerprint, never the
    # run id or a wall-clock timestamp. Two runs of the same snapshot, config,
    # and code must produce byte-identical journals (SC-004), and a start time
    # in the header would break that on the first line.
    lines = [
        f"# Decision Journal — {symbol}",
        "",
        f"**Fingerprint**: `{fingerprint}`  ",
        f"**Snapshot**: `{snapshot_id}`  ",
        f"**Config**: `{config_version}`",
        "",
        f"{len(decisions)} decisions over {len(decisions)} completed bars — "
        f"{counts['ENTER']} entries, {counts['EXIT']} exits, {counts['HOLD']} holds, "
        f"{counts['SKIP']} skips. {len(trades)} completed trades.",
        "",
        "---",
        "",
    ]

    for decision in decisions:
        if not include_holds and decision.action is Action.HOLD:
            continue
        lines += [
            f"## {decision.as_of.date().isoformat()} — {decision.action.value}",
            "",
            explain(decision),
            "",
        ]
        if decision.action is Action.ENTER and decision.plan is not None:
            plan = decision.plan
            lines += [
                "| | |",
                "|---|---|",
                f"| Shares | {plan.shares} |",
                f"| Stop | {plan.stop:.2f} |",
                f"| Risk | {plan.risk_amount:.2f} ({plan.risk_pct:.2%}) |",
                f"| Sized by | {plan.binding_constraint.value} |",
                "",
            ]
        lines.append("")

    return "\n".join(lines)


def trades_table(trades: list[Trade]) -> Table:
    table = Table(title="Completed trades", show_lines=False)
    for column in ("Opened", "Closed", "Shares", "Exit", "Result", "R", "Over plan"):
        table.add_column(column)
    for trade in trades:
        overrun = f"{trade.risk_overrun:,.2f}" if trade.risk_overrun > 0 else "—"
        table.add_row(
            trade.entry_fill.at.date().isoformat(),
            trade.exit_fill.at.date().isoformat(),
            str(trade.shares),
            trade.exit_reason.value,
            f"{trade.result_currency:+,.2f}",
            f"{trade.result_r:+.2f}",
            overrun,
        )
    return table


def print_decision(console: Console, decision: Decision) -> None:
    """One decision, as it happens."""
    style = ACTION_STYLE[decision.action]
    console.print(f"[{style}]{one_line(decision)}[/{style}]")
    for verdict in decision.verdicts:
        mark = "[green]OK  [/green]" if verdict.passed else "[red]NO  [/red]"
        console.print(f"      {mark} {verdict.statement}", highlight=False)
    console.print()


def print_summary(console: Console, decisions: list[Decision], trades: list[Trade]) -> None:
    counts = {a.value: 0 for a in Action}
    for decision in decisions:
        counts[decision.action.value] += 1
    console.print(
        f"[bold]{len(decisions)}[/bold] decisions "
        f"(enter {counts['ENTER']}, exit {counts['EXIT']}, "
        f"hold {counts['HOLD']}, skip {counts['SKIP']}) — "
        f"every completed bar accounted for."
    )
    if trades:
        console.print(trades_table(trades))
