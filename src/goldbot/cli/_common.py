"""Shared CLI plumbing: paths, exit codes, and error mapping.

The exit codes are distinct on purpose (contracts/cli.md). Code 3 means the
data is wrong, 4 means the code tried something forbidden, 5 means the system
stopped itself. Collapsing them would make a guard firing — the most important
signal this system produces — look like a failed download.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar

import typer
from rich.console import Console

from goldbot.domain.errors import ConfigError, DataIntegrityError, GuardViolation, HaltRequired

console = Console()
err_console = Console(stderr=True)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_DATA = 3
EXIT_GUARD = 4
EXIT_HALT = 5

REPO_ROOT = Path.cwd()
DATA_RAW = Path("data/raw")
DATA_SNAPSHOTS = Path("data/snapshots")
RUNS_DIR = Path("runs")
AUDIT_DB = RUNS_DIR / "audit.db"
KILL_LATCH = RUNS_DIR / "kill.latch"

#: Below this, whole-share rounding makes the 1% rule approximate at best.
SMALL_ACCOUNT_THRESHOLD = Decimal("5000")

F = TypeVar("F", bound=Callable[..., Any])


def code_version() -> str:
    """Git commit, marked dirty when the tree has uncommitted changes.

    Part of the reproducibility triple: a result is only reproducible if you
    know which code produced it.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if commit.returncode != 0:
            return "no-git"
        sha = commit.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return f"{sha}-dirty" if status.stdout.strip() else sha
    except (OSError, subprocess.SubprocessError):
        return "no-git"


def fingerprint(snapshot_digest: str | None, config_version: str, code: str) -> str:
    """The reproducibility triple, hashed.

    Identical fingerprint means the run should be byte-identical. It goes in
    the journal header instead of a run id so that two runs of the same inputs
    produce the same file.
    """
    payload = f"{snapshot_digest or 'live'}|{config_version}|{code}"
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def new_run_id(symbol: str, mode: str, print_: str) -> str:
    """Unique per invocation, so repeated runs coexist in one audit store."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"{symbol}-{mode.lower()}-{stamp}-{print_[:8]}"


def warn_small_account(equity: Decimal) -> None:
    """Surface the quantisation problem at startup, not in a confusing journal entry."""
    if equity >= SMALL_ACCOUNT_THRESHOLD:
        return
    err_console.print(
        f"[yellow]Note:[/yellow] equity of {equity:,.2f} is small enough that whole-share "
        "rounding makes the 1% risk rule approximate — a single share can be several "
        "percent of the account. This is a property of trading ETF shares, not a defect. "
        "Run [bold]goldbot lessons show position-sizing[/bold] for the detail."
    )


def guarded(func: F) -> F:
    """Map domain exceptions onto the documented exit codes."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except DataIntegrityError as exc:
            err_console.print(f"[red]Data integrity failure:[/red] {exc}")
            raise typer.Exit(EXIT_DATA) from exc
        except GuardViolation as exc:
            err_console.print(f"[red]Guard triggered:[/red] {exc}")
            err_console.print(
                "[dim]A guard firing means the code asked for something the constitution "
                "forbids. This is the system working.[/dim]"
            )
            raise typer.Exit(EXIT_GUARD) from exc
        except HaltRequired as exc:
            err_console.print(f"[yellow]Halted:[/yellow] {exc}")
            raise typer.Exit(EXIT_HALT) from exc
        except ConfigError as exc:
            err_console.print(f"[red]Configuration problem:[/red] {exc}")
            raise typer.Exit(EXIT_USAGE) from exc

    return wrapper  # type: ignore[return-value]
