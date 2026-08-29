"""`goldbot paper` — forward testing with simulated fills.

No order is transmitted anywhere. There is no code path that could.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import typer

from goldbot.cli._common import (
    AUDIT_DB,
    DATA_SNAPSHOTS,
    EXIT_HALT,
    KILL_LATCH,
    RUNS_DIR,
    code_version,
    console,
    err_console,
    fingerprint,
    guarded,
    new_run_id,
    warn_small_account,
)
from goldbot.config import load_config
from goldbot.data.snapshot import find_manifest, load_bars, verify
from goldbot.engine.paper import PaperState, run_session, write_resume_date
from goldbot.engine.promotion import PromotionState, Stage
from goldbot.journal.render import print_decision
from goldbot.journal.store import AuditStore

app = typer.Typer(help="Forward-test with live data and simulated fills.")

PROMOTION_PATH = RUNS_DIR / "promotion.json"
STATE_PATH = RUNS_DIR / "paper" / "state.json"


def _report(state: PaperState) -> None:
    console.print()
    print_decision(console, state.latest_decision)
    console.print(f"  equity        {state.equity:,.2f}")
    console.print(f"  trades so far {state.trades}")
    console.print("  execution     [bold]simulated[/bold]  [dim]no order leaves this process[/dim]")
    if state.next_session_open:
        console.print(f"  next open     {state.next_session_open.isoformat()}")
    if state.halted:
        console.print(f"\n[yellow]HALTED[/yellow] {state.halt_reason}")
        console.print("[dim]Clear it with `goldbot paper resume` when you have reviewed why.[/dim]")


@app.command("run")
@guarded
def run(
    config_path: Path = typer.Option(
        Path("config/baseline.toml"), "--config", help="Strategy configuration"
    ),
    snapshot: str = typer.Option(..., "--snapshot", help="Snapshot providing the price history"),
    cadence: str = typer.Option("daily", "--cadence", help="daily | 4h"),
    safe_mode: bool = typer.Option(
        False, "--safe-mode", help="Continue under stale data without opening anything"
    ),
    skip_promotion_check: bool = typer.Option(
        False, "--skip-promotion-check", help="Bypass the backtest/walk-forward gate (not advised)"
    ),
) -> None:
    """Advance the paper session by replaying history through the same engine."""
    config = load_config(config_path)
    config.instrument
    warn_small_account(config.initial_equity)

    if not skip_promotion_check:
        promotion = PromotionState.load(PROMOTION_PATH, config.version)
        promotion.require(Stage.PAPER)

    manifest = find_manifest(DATA_SNAPSHOTS, snapshot)
    verify(manifest, root=Path.cwd())
    bars = load_bars(Path(manifest.data_path), config.symbol)

    code = code_version()
    print_ = fingerprint(manifest.sha256, config.version, code)
    run_id = new_run_id(config.symbol, "paper", print_)

    console.print(f"Paper session for {config.symbol} — {len(bars)} bars of history")
    console.print(f"Risk envelope: {config.envelope.describe()}\n")

    with AuditStore(AUDIT_DB) as store:
        store.start_run(
            run_id=run_id,
            mode="PAPER",
            symbol=config.symbol,
            snapshot_digest=None,
            config_version=config.version,
            envelope_version=config.envelope.version,
            code_version=code,
            started_at=datetime.now(UTC),
        )
        try:
            _, state = run_session(
                config=config,
                bars=bars,
                run_id=run_id,
                store=store,
                kill_latch=KILL_LATCH,
                runs_root=RUNS_DIR,
                safe_mode=safe_mode,
            )
        except Exception:
            store.append_run_event(run_id, datetime.now(UTC), "ABORTED")
            raise
        store.append_run_event(
            run_id,
            datetime.now(UTC),
            "HALTED" if state.halted else "COMPLETE",
        )

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(state.to_json() + "\n", encoding="utf-8")

    if state.stale:
        err_console.print(f"[yellow]SAFE mode:[/yellow] {state.stale_reason}")

    _report(state)

    if state.halted:
        raise typer.Exit(EXIT_HALT)


@app.command("status")
def status() -> None:
    """Show the state left by the last session step."""
    if not STATE_PATH.exists():
        console.print("No paper session has run yet.")
        return
    console.print(STATE_PATH.read_text(encoding="utf-8"))


@app.command("resume")
def resume(
    note: str = typer.Option("", "--note", help="Why you are resuming"),
) -> None:
    """Clear a daily-loss halt. Requires a deliberate act, by design (FR-014)."""
    today = date.today()
    write_resume_date(RUNS_DIR, today, note)
    console.print(f"[green]Resumed.[/green] Halts before {today.isoformat()} are cleared.")
    console.print(
        "[dim]The limit existed for a reason. If you are clearing it because the setup "
        "looked too good to miss, that is the situation it was written for.[/dim]"
    )
