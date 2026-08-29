"""`goldbot kill` — stop everything, and stay stopped."""

from __future__ import annotations

from datetime import UTC, datetime

import typer

from goldbot.cli._common import AUDIT_DB, KILL_LATCH, console
from goldbot.journal.store import AuditStore
from goldbot.risk.kill_switch import KillSwitch


def kill(
    clear: bool = typer.Option(False, "--clear", help="Release the latch"),
    note: str = typer.Option("", "--note", help="Why"),
) -> None:
    """Cancel working orders, flatten positions, and latch the system shut.

    Safe to run when nothing is open — it is idempotent. Nothing releases the
    latch except `--clear`: not a restart, not midnight, not a new session.
    """
    switch = KillSwitch(KILL_LATCH)

    if clear:
        if switch.clear():
            console.print("[green]Kill switch cleared.[/green] New entries are allowed again.")
        else:
            console.print("The kill switch was not engaged. Nothing to clear.")
        return

    now = datetime.now(UTC)
    # Paper sessions hold no state between invocations — they are reconstructed
    # by replay — so there is nothing live to cancel. The latch is what stops
    # the next session from opening anything.
    result = switch.engage(at=now, cancel=0, flatten=0, note=note)

    if result.already_engaged:
        console.print("[yellow]Already engaged.[/yellow]")
        console.print(f"  {switch.reason()}")
        return

    try:
        with AuditStore(AUDIT_DB) as store:
            runs = store.runs()
            if runs:
                store.record_halt(
                    runs[0]["run_id"],
                    now,
                    "KILL_SWITCH",
                    note or "Kill switch engaged by the operator.",
                )
    except Exception:  # noqa: BLE001 - the latch matters more than the audit row
        console.print("[yellow]Latch set, but the halt could not be recorded.[/yellow]")

    console.print(f"[red]Kill switch engaged[/red] in {result.elapsed_seconds:.3f}s")
    console.print(f"  orders cancelled    {result.orders_cancelled}")
    console.print(f"  positions flattened {result.positions_flattened}")
    console.print(f"  latch               {result.latch_path}")
    console.print("\nNew entries are blocked until `goldbot kill --clear`.")
