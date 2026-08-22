"""The goldbot command line.

Every command here is incapable of placing a real order, because no code path
in this package can (FR-024). `--version` says so out loud, so an operator can
confirm it without reading the source.
"""

from __future__ import annotations

import typer

from goldbot.cli import backtest as backtest_cmd
from goldbot.cli import data as data_cmd
from goldbot.cli import journal as journal_cmd
from goldbot.cli import report as report_cmd
from goldbot.cli._common import console

app = typer.Typer(
    help=(
        "A gold ETF trading bot that explains every decision it makes.\n\n"
        "Execution is simulated only — this version has no live trading path."
    ),
    no_args_is_help=True,
    add_completion=False,
)

app.add_typer(data_cmd.app, name="data")
app.add_typer(journal_cmd.app, name="journal")
app.command("backtest")(backtest_cmd.backtest)
app.command("report")(report_cmd.report)


@app.command("version")
def version() -> None:
    """Show the version and confirm the execution mode."""
    from importlib.metadata import PackageNotFoundError, version as pkg_version

    try:
        installed = pkg_version("goldbot")
    except PackageNotFoundError:
        installed = "0.1.0 (not installed)"

    console.print(f"goldbot {installed}")
    console.print("execution: [bold]simulated only[/bold]")
    console.print(
        "[dim]No brokerage trading client is installed and no code path can transmit an "
        "order. Enabling live execution requires a separate, specified feature.[/dim]"
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
