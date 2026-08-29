"""`goldbot walkforward` — evaluate on data that was never used to choose parameters.

A backtest tells you how a strategy would have done on the data you looked at
while building it. That is not evidence. Walk-forward splits the history: the
parameters are fixed on the earlier part, the result is measured on the later
part, and only the second number means anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, date as date_type
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
)
from goldbot.config import load_config
from goldbot.data.snapshot import find_manifest, load_bars, verify
from goldbot.engine.promotion import PromotionState, Stage
from goldbot.engine.runner import execute
from goldbot.journal import report as report_module
from goldbot.journal.store import AuditStore

PROMOTION_PATH = RUNS_DIR / "promotion.json"


@guarded
def walkforward(
    snapshot: str = typer.Option(..., "--snapshot", help="Snapshot id"),
    config_path: Path = typer.Option(
        Path("config/baseline.toml"), "--config", help="Strategy configuration"
    ),
    train_until: str = typer.Option(
        ..., "--train-until", help="YYYY-MM-DD; everything after this is the held-out test"
    ),
    min_expectancy: str = typer.Option(
        "0.0", "--min-expectancy", help="Acceptance criterion, in R per trade"
    ),
    min_trades: int = typer.Option(10, "--min-trades", help="Acceptance criterion"),
) -> None:
    """Measure the strategy on held-out data and record whether it passed."""
    from decimal import Decimal

    config = load_config(config_path)
    config.instrument

    promotion = PromotionState.load(PROMOTION_PATH, config.version)
    promotion.require(Stage.WALK_FORWARD)

    manifest = find_manifest(DATA_SNAPSHOTS, snapshot)
    verify(manifest, root=Path.cwd())
    all_bars = load_bars(Path(manifest.data_path), config.symbol)

    cutoff = date_type.fromisoformat(train_until)
    test_bars = tuple(b for b in all_bars if b.end.date() > cutoff)
    if len(test_bars) < config.strategy.min_history + 20:
        raise typer.BadParameter(
            f"only {len(test_bars)} bars after {cutoff}; the strategy needs "
            f"{config.strategy.min_history} just to warm up. Move --train-until earlier."
        )

    code = code_version()
    print_ = fingerprint(manifest.sha256, config.version, code)
    run_id = new_run_id(config.symbol, "walkforward", print_)

    console.print(
        f"Walk-forward on {len(test_bars)} held-out bars after {cutoff} "
        f"[dim](of {len(all_bars)} total)[/dim]"
    )
    console.print(
        f"Acceptance, declared before the run: expectancy >= {min_expectancy} R "
        f"over at least {min_trades} trades\n"
    )

    with AuditStore(AUDIT_DB) as store:
        artifacts = execute(
            config=config,
            bars=test_bars,
            snapshot_id=manifest.snapshot_id,
            snapshot_digest=manifest.sha256,
            code_version=code,
            fingerprint=print_,
            run_id=run_id,
            out_dir=RUNS_DIR / run_id,
            store=store,
            mode="WALK_FORWARD",
        )

    metrics = artifacts.metrics
    console.print(report_module.render(metrics, cadence=config.cadence))
    console.print()

    passed = metrics.expectancy_r >= Decimal(min_expectancy) and metrics.trade_count >= min_trades
    if passed:
        promotion.record(
            Stage.WALK_FORWARD,
            run_id=run_id,
            at=datetime.now(UTC),
            expectancy_r=str(metrics.expectancy_r),
            trade_count=metrics.trade_count,
            note=f"expectancy >= {min_expectancy} over >= {min_trades} trades",
        )
        promotion.save(PROMOTION_PATH)
        console.print("[green]PASSED[/green] — paper trading is now unlocked for this config.")
    else:
        err_console.print(
            f"[yellow]NOT PASSED[/yellow] — expectancy {metrics.expectancy_r:+.3f} R over "
            f"{metrics.trade_count} trades did not meet the criteria declared above."
        )
        err_console.print(
            "[dim]This is the system working. A strategy that fails here has been stopped "
            "before it cost anything.[/dim]"
        )


@guarded
def promote(
    config_path: Path = typer.Option(
        Path("config/baseline.toml"), "--config", help="Strategy configuration"
    ),
    stage: str = typer.Option(..., "--to", help="backtest | walk_forward"),
    run: str = typer.Option(..., "--run", help="Run id that justifies the promotion"),
) -> None:
    """Record that a stage passed, citing the run that proves it."""
    config = load_config(config_path)
    target = Stage(stage.upper())
    if target is Stage.PAPER:
        raise typer.BadParameter(
            "paper is unlocked by a passing walk-forward run, not by hand. "
            "Run `goldbot walkforward`."
        )

    promotion = PromotionState.load(PROMOTION_PATH, config.version)
    with AuditStore(AUDIT_DB) as store:
        row = store.run(run)
        if row is None:
            raise typer.BadParameter(f"no run {run!r}")
        trades = store.trades_for_run(run)

    promotion.record(
        target,
        run_id=run,
        at=datetime.now(UTC),
        expectancy_r="recorded-by-hand",
        trade_count=len(trades),
        note="promoted manually",
    )
    promotion.save(PROMOTION_PATH)
    console.print(f"[green]{target.value} recorded as passed[/green] on the evidence of {run}.")


def promotion_status(
    config_path: Path = typer.Option(
        Path("config/baseline.toml"), "--config", help="Strategy configuration"
    ),
) -> None:
    """Show which stages this configuration has cleared."""
    config = load_config(config_path)
    promotion = PromotionState.load(PROMOTION_PATH, config.version)
    console.print(f"Config {config.version}\n")
    for stage in Stage:
        if promotion.has_passed(stage):
            record = promotion.passes[stage.value]
            console.print(
                f"  [green]PASSED[/green]  {stage.value:<13} "
                f"[dim]{record.trade_count} trades, {record.run_id}[/dim]"
            )
        else:
            missing = promotion.missing_for(stage)
            blocked = f" [dim](needs {', '.join(s.value for s in missing)})[/dim]" if missing else ""
            console.print(f"  [dim]—[/dim]       {stage.value:<13}{blocked}")
    console.print("\n[dim]LIVE is not a stage in this version. It does not exist in code.[/dim]")
