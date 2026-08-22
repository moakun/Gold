"""Running a full backtest inside a test, entirely offline.

Everything comes from committed fixtures. No network, no credentials — which is
possible only because the default data path needs neither.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

from goldbot.config import Config, load_config
from goldbot.data.snapshot import Manifest, load_bars, write_manifest
from goldbot.engine.runner import RunArtifacts, execute
from goldbot.journal.store import AuditStore

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BASELINE = Path(__file__).resolve().parents[2] / "config" / "baseline.toml"


def pin_fixture(tmp_path: Path, fixture: str = "gld_daily.csv", symbol: str = "GLD") -> Manifest:
    """Copy a fixture into a temporary data tree and pin it."""
    raw_dir = tmp_path / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / fixture
    shutil.copy(FIXTURES / fixture, target)
    return write_manifest(
        manifest_dir=tmp_path / "data" / "snapshots",
        data_path=target,
        symbol=symbol,
        cadence="daily",
        source="fixture",
        fetched_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        notes="Committed test fixture.",
    )


def load_baseline(**overrides: object) -> Config:
    """The shipped baseline config, optionally patched for a specific test."""
    config = load_baseline_raw()
    if not overrides:
        return config
    from dataclasses import replace

    return replace(config, **overrides)  # type: ignore[arg-type]


def load_baseline_raw() -> Config:
    return load_config(BASELINE)


def run_backtest(
    tmp_path: Path,
    *,
    fixture: str = "gld_daily.csv",
    config: Config | None = None,
    run_id: str = "test-run",
    out_name: str = "out",
) -> tuple[RunArtifacts, Manifest]:
    manifest = pin_fixture(tmp_path, fixture)
    cfg = config or load_baseline_raw()
    bars = load_bars(Path(manifest.data_path), cfg.symbol)

    with AuditStore(tmp_path / f"{run_id}-audit.db") as store:
        artifacts = execute(
            config=cfg,
            bars=bars,
            snapshot_id=manifest.snapshot_id,
            snapshot_digest=manifest.sha256,
            code_version="test-code",
            fingerprint="test-print",
            run_id=run_id,
            out_dir=tmp_path / out_name,
            store=store,
        )
    return artifacts, manifest
