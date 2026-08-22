"""`goldbot journal` — why did the system do that?

`journal why --date` is the SC-007 path: one command, under a minute, full
reasoning for what happened on a given day, including the days it did nothing.
"""

from __future__ import annotations

import json
from datetime import date

import typer

from goldbot.cli._common import AUDIT_DB, console, err_console
from goldbot.journal.store import AuditStore

app = typer.Typer(help="Read the decision journal.")


def _render_rows(store: AuditStore, rows: list, as_json: bool) -> None:
    if as_json:
        payload = []
        for row in rows:
            verdicts = store.verdicts_for(row["decision_id"])
            payload.append(
                {
                    "decision_id": row["decision_id"],
                    "as_of": row["as_of"],
                    "symbol": row["symbol"],
                    "action": row["action"],
                    "explanation": row["explanation"],
                    "blocking_rule_id": row["blocking_rule_id"],
                    "plan": json.loads(row["plan_json"]) if row["plan_json"] else None,
                    "verdicts": [
                        {
                            "rule_id": v["rule_id"],
                            "principle": v["principle"],
                            "passed": bool(v["passed"]),
                            "evidence": json.loads(v["evidence_json"]),
                            "statement": v["statement"],
                        }
                        for v in verdicts
                    ],
                }
            )
        console.print_json(json.dumps(payload))
        return

    for row in rows:
        console.print(f"[bold]{row['as_of'][:10]}  {row['action']}[/bold]  {row['symbol']}")
        console.print(row["explanation"])
        console.print()


@app.command("show")
def show(
    run: str = typer.Option(None, "--run", help="Run id"),
    day: str = typer.Option(None, "--date", help="YYYY-MM-DD"),
    decision: str = typer.Option(None, "--decision", help="Decision id"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Show decisions by run, date, or id."""
    with AuditStore(AUDIT_DB) as store:
        if decision:
            row = store.decision(decision)
            if row is None:
                err_console.print(f"No decision {decision!r}.")
                raise typer.Exit(2)
            _render_rows(store, [row], as_json)
        elif day:
            _render_rows(store, store.decisions_on(date.fromisoformat(day)), as_json)
        elif run:
            _render_rows(store, store.decisions_for_run(run), as_json)
        else:
            raise typer.BadParameter("give one of --run, --date, or --decision")


@app.command("why")
def why(
    day: str = typer.Argument(None, help="YYYY-MM-DD"),
    date_opt: str = typer.Option(None, "--date", help="YYYY-MM-DD"),
) -> None:
    """Full reasoning for one day — including why nothing happened."""
    target = day or date_opt
    if not target:
        raise typer.BadParameter("give a date, e.g. `goldbot journal why 2026-03-14`")

    with AuditStore(AUDIT_DB) as store:
        rows = store.decisions_on(date.fromisoformat(target))
        if not rows:
            console.print(
                f"No decision recorded for {target}. Either the market was closed, or no "
                "run has covered that date yet."
            )
            return

        for row in rows:
            console.print(f"[bold]{target} — {row['action']}[/bold]  ({row['symbol']})")
            console.print()
            console.print(row["explanation"])
            console.print()
            console.print("[dim]Every rule that was evaluated:[/dim]")
            for verdict in store.verdicts_for(row["decision_id"]):
                mark = "[green]OK[/green]" if verdict["passed"] else "[red]NO[/red]"
                console.print(f"  {mark}  [dim]{verdict['rule_id']}[/dim]  {verdict['statement']}")
                console.print(
                    f"      [dim]principle: {verdict['principle']} — "
                    f"`goldbot lessons show {verdict['principle']}`[/dim]"
                )
            console.print()


@app.command("runs")
def runs() -> None:
    """List recorded runs."""
    with AuditStore(AUDIT_DB) as store:
        rows = store.runs()
        if not rows:
            console.print("No runs recorded yet.")
            return
        for row in rows:
            status = store.run_status(row["run_id"])
            console.print(
                f"{row['run_id']}  [dim]{row['mode']}  {status}  "
                f"snapshot {(row['snapshot_digest'] or 'live')[:12]}[/dim]"
            )
