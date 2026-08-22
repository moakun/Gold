"""`goldbot data` — fetching and pinning snapshots."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import typer

from goldbot.cli._common import DATA_RAW, DATA_SNAPSHOTS, EXIT_DATA, console, err_console, guarded
from goldbot.data.snapshot import Manifest, digest_of, verify
from goldbot.data.sources import stooq
from goldbot.domain.errors import DataIntegrityError

app = typer.Typer(help="Fetch and verify pinned market data snapshots.")


@app.command("pull")
@guarded
def pull(
    symbol: str = typer.Option(..., "--symbol", help="Ticker, e.g. GLD"),
    start: str = typer.Option(..., "--from", help="Start date, YYYY-MM-DD"),
    end: str = typer.Option(..., "--to", help="End date, YYYY-MM-DD"),
    source: str = typer.Option("stooq", "--source", help="stooq | tiingo | alpaca"),
    cadence: str = typer.Option("daily", "--cadence", help="daily | 4h"),
) -> None:
    """Fetch bars, write them, and pin them with a manifest.

    The default source needs no credentials, so this whole path runs with no
    secrets at all.
    """
    from goldbot.data.snapshot import write_manifest

    if source == "alpaca" and cadence != "4h":
        raise typer.BadParameter("--source alpaca is only for --cadence 4h")
    if cadence == "4h" and source == "stooq":
        raise typer.BadParameter(
            "Stooq is end-of-day only. For --cadence 4h use --source alpaca, which needs "
            "ALPACA_API_KEY and ALPACA_API_SECRET in the environment."
        )

    from_date, to_date = date.fromisoformat(start), date.fromisoformat(end)
    DATA_RAW.mkdir(parents=True, exist_ok=True)

    console.print(f"Fetching {symbol} {cadence} bars from {source}, {from_date} to {to_date}…")
    if source == "stooq":
        payload = stooq.fetch_daily(symbol, from_date, to_date)
    elif source == "tiingo":
        from goldbot.data.sources import tiingo

        payload = tiingo.fetch_daily(symbol, from_date, to_date)
    elif source == "alpaca":
        from goldbot.data.sources import alpaca_intraday

        payload = alpaca_intraday.fetch_4h(symbol, from_date, to_date)
    else:
        raise typer.BadParameter(f"unknown source {source!r}")

    target = DATA_RAW / f"{symbol.upper()}-{cadence}-{from_date}-{to_date}.csv"
    target.write_bytes(payload)

    manifest = write_manifest(
        manifest_dir=DATA_SNAPSHOTS,
        data_path=target,
        symbol=symbol,
        cadence=cadence,
        source=source,
        fetched_at=datetime.now(UTC),
        notes="Adjusted for splits. No dividend adjustment (fund pays none).",
    )
    console.print(
        f"[green]Pinned[/green] {manifest.snapshot_id}: {manifest.row_count} rows, "
        f"{manifest.range_from} to {manifest.range_to}"
    )
    console.print(f"  digest   {manifest.sha256[:32]}…")
    console.print(f"  data     {manifest.data_path}  [dim](gitignored)[/dim]")
    console.print(f"  manifest {DATA_SNAPSHOTS}/{manifest.snapshot_id}.manifest.json  [dim](tracked)[/dim]")


@app.command("verify")
def verify_command(
    snapshot: str = typer.Option(None, "--snapshot", help="Snapshot id, or all if omitted"),
) -> None:
    """Recompute digests and compare against the manifests."""
    manifests = sorted(DATA_SNAPSHOTS.glob("*.manifest.json"))
    if snapshot:
        manifests = [p for p in manifests if p.name.startswith(snapshot)]
    if not manifests:
        err_console.print("[yellow]No snapshots found.[/yellow] Run `goldbot data pull` first.")
        raise typer.Exit(EXIT_DATA)

    failures = 0
    for path in manifests:
        manifest = Manifest.from_path(path)
        try:
            verify(manifest, root=Path.cwd())
        except DataIntegrityError as exc:
            failures += 1
            err_console.print(f"[red]FAIL[/red] {manifest.snapshot_id}")
            err_console.print(f"      {exc}")
        else:
            console.print(f"[green]ok[/green]   {manifest.snapshot_id}  ({manifest.row_count} rows)")

    if failures:
        err_console.print(
            f"\n[red]{failures} snapshot(s) do not match their manifests.[/red] "
            "A backtest against changed data is not the backtest the manifest describes."
        )
        raise typer.Exit(EXIT_DATA)


@app.command("list")
def list_snapshots() -> None:
    """Show pinned snapshots."""
    manifests = sorted(DATA_SNAPSHOTS.glob("*.manifest.json"))
    if not manifests:
        console.print("No snapshots pinned yet.")
        return
    for path in manifests:
        manifest = Manifest.from_path(path)
        console.print(
            f"{manifest.snapshot_id}  [dim]{manifest.row_count} rows, "
            f"{manifest.source}, {manifest.sha256[:12]}…[/dim]"
        )


__all__ = ["app", "digest_of"]
