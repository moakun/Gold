"""`goldbot report` — the whole metric set, or nothing.

There is deliberately no `--metric` flag. FR-026 exists because a single number
quoted alone is how people mislead themselves: a 70% win rate says nothing
without the average loss, and a return figure says nothing without the
drawdown that produced it.
"""

from __future__ import annotations

from decimal import Decimal

import typer

from goldbot.cli._common import AUDIT_DB, console, err_console
from goldbot.domain.money import ZERO, dec
from goldbot.journal.store import AuditStore


def report(run: str = typer.Option(..., "--run", help="Run id")) -> None:
    """Rebuild the performance report for a recorded run, from the audit store."""
    with AuditStore(AUDIT_DB) as store:
        run_row = store.run(run)
        if run_row is None:
            err_console.print(f"No run {run!r}. Try `goldbot journal runs`.")
            raise typer.Exit(2)

        trades = store.trades_for_run(run)
        decisions = store.decisions_for_run(run)
        halts = store.halts_for_run(run)
        violations = store.violations_for_run(run)

        console.print(f"[bold]{run}[/bold]  {run_row['mode']}  {store.run_status(run)}")
        console.print(
            f"snapshot {(run_row['snapshot_digest'] or 'live')[:16]}  "
            f"config {run_row['config_version']}  code {run_row['code_version']}"
        )
        console.print(f"{len(decisions)} decisions, {len(trades)} trades\n")

        if not trades:
            console.print("No completed trades in this run.")
        else:
            wins = [t for t in trades if dec(t["result_currency"]) > ZERO]
            total: Decimal = sum((dec(t["result_currency"]) for t in trades), ZERO)
            r_values = [dec(t["result_r"]) for t in trades]
            overruns = [t for t in trades if dec(t["risk_overrun"]) > ZERO]

            console.print("PERFORMANCE")
            console.print("=" * 68)
            console.print(f"  Trades              {len(trades)}")
            console.print(
                f"  Win rate            {len(wins) / len(trades):.1%}  "
                f"({len(wins)} won, {len(trades) - len(wins)} lost)"
            )
            console.print(
                f"  Expectancy          {sum(r_values, ZERO) / len(r_values):+.3f} R per trade"
            )
            console.print(f"  Net result          {total:+,.2f}")
            console.print()
            console.print("DID THE RISK LIMIT ACTUALLY HOLD?")
            console.print("-" * 68)
            console.print(f"  Trades over plan    {len(overruns)}")
            console.print(
                f"  Excess loss         "
                f"{sum((dec(t['risk_overrun']) for t in overruns), ZERO):,.2f}"
            )
            console.print()
            console.print("LOSSES, CLASSIFIED")
            console.print("-" * 68)
            for label, key in (
                ("Correctly taken", "CORRECT"),
                ("Rule violations", "RULE_VIOLATION"),
                ("System errors", "SYSTEM_ERROR"),
            ):
                count = sum(1 for t in trades if t["classification"] == key)
                console.print(f"  {label:<20}{count}")

        console.print()
        console.print(f"Halts recorded      {len(halts)}")
        console.print(f"Guard refusals      {len(violations)}")
        if not violations:
            console.print(
                "[dim]  No refusals in this run. Worth noticing: it means the guards were "
                "never exercised, not that they work.[/dim]"
            )
