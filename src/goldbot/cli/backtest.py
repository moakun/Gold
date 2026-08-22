"""`goldbot backtest` — run the strategy over a pinned snapshot."""

from __future__ import annotations

from pathlib import Path

import typer

from goldbot.cli._common import (
    AUDIT_DB,
    DATA_SNAPSHOTS,
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
from goldbot.data.feed import HistoricalFeed
from goldbot.data.snapshot import find_manifest, load_bars, verify
from goldbot.engine.runner import execute
from goldbot.journal import report as report_module
from goldbot.journal.render import print_summary
from goldbot.journal.store import AuditStore


@guarded
def backtest(
    snapshot: str = typer.Option(..., "--snapshot", help="Snapshot id from `goldbot data list`"),
    config_path: Path = typer.Option(
        Path("config/baseline.toml"), "--config", help="Strategy configuration"
    ),
    out: Path = typer.Option(None, "--out", help="Where to write journal and report"),
) -> None:
    """Replay a strategy over pinned history, explaining every bar.

    Refuses to start if the snapshot no longer matches its manifest — a
    backtest against changed data is not the backtest the manifest describes.
    """
    config = load_config(config_path)
    # Check the allow-list before anything is recorded. Failing here rather
    # than part-way through leaves no orphan run row for a symbol that was
    # never tradable in the first place.
    config.instrument
    warn_small_account(config.initial_equity)

    manifest = find_manifest(DATA_SNAPSHOTS, snapshot)
    verify(manifest, root=Path.cwd())

    bars = load_bars(Path(manifest.data_path), config.symbol)
    feed = HistoricalFeed(bars, digest=manifest.sha256)

    if feed.gaps:
        err_console.print(
            f"[yellow]{len(feed.gaps)} data gap(s) in this snapshot.[/yellow] "
            "Gaps are reported, never interpolated:"
        )
        for gap in feed.gaps[:5]:
            err_console.print(f"  {gap.describe()}")

    code = code_version()
    print_ = fingerprint(manifest.sha256, config.version, code)
    run_id = new_run_id(config.symbol, "backtest", print_)
    out_dir = out or (RUNS_DIR / run_id)

    console.print(
        f"Backtesting {config.symbol} over {len(feed)} bars "
        f"[dim]({manifest.range_from} to {manifest.range_to})[/dim]"
    )
    console.print(f"Risk envelope: {config.envelope.describe()}")
    console.print(f"Fingerprint: [bold]{print_}[/bold]  [dim]same inputs, same journal[/dim]\n")

    with AuditStore(AUDIT_DB) as store:
        artifacts = execute(
            config=config,
            bars=feed.all_bars,
            snapshot_id=manifest.snapshot_id,
            snapshot_digest=manifest.sha256,
            code_version=code,
            fingerprint=print_,
            run_id=run_id,
            out_dir=out_dir,
            store=store,
        )

    result = artifacts.result
    counts = result.action_counts
    console.print(
        f"[bold]{len(result.decisions)}[/bold] decisions over "
        f"[bold]{result.bars_evaluated}[/bold] completed bars "
        f"(enter {counts['ENTER']}, exit {counts['EXIT']}, hold {counts['HOLD']}, "
        f"skip {counts['SKIP']})"
    )
    if len(result.decisions) != result.bars_evaluated:
        err_console.print("[red]Decision count does not match bar count — that is a defect.[/red]")

    print_summary(console, result.decisions, result.trades)
    console.print()
    console.print(report_module.render(artifacts.metrics, cadence=config.cadence))
    console.print()
    console.print(f"Journal  {artifacts.journal_path}")
    console.print(f"Report   {artifacts.report_path}")
    console.print(f"Run id   {artifacts.run_id}")

    if result.halts:
        console.print(f"\n[yellow]{len(result.halts)} daily-loss halt(s) during this run.[/yellow]")
