"""Pinned data, and what happens when it moves.

Refusing to run against altered data is the feature. A backtest whose inputs
changed silently is not the backtest its manifest describes, and every number
it produces is uncheckable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from goldbot.data.snapshot import Manifest, load_bars, verify
from goldbot.domain.errors import DataIntegrityError
from tests.integration._helpers import pin_fixture


def test_a_pinned_snapshot_verifies(tmp_path: Path) -> None:
    manifest = pin_fixture(tmp_path)
    verify(manifest, root=Path.cwd())
    assert manifest.row_count == 400
    assert len(manifest.sha256) == 64


def test_a_single_changed_byte_is_caught(tmp_path: Path) -> None:
    manifest = pin_fixture(tmp_path)
    data = Path(manifest.data_path)

    content = data.read_text(encoding="utf-8")
    data.write_text(content.replace("200.76", "200.77", 1), encoding="utf-8")

    with pytest.raises(DataIntegrityError, match="does not match its manifest"):
        verify(manifest, root=Path.cwd())


def test_missing_data_is_reported_helpfully(tmp_path: Path) -> None:
    manifest = pin_fixture(tmp_path)
    Path(manifest.data_path).unlink()
    with pytest.raises(DataIntegrityError, match="gitignored"):
        verify(manifest, root=Path.cwd())


def test_repinning_changed_data_refuses_to_overwrite(tmp_path: Path) -> None:
    """An old backtest must stay reproducible even after upstream changes."""
    manifest = pin_fixture(tmp_path)
    data = Path(manifest.data_path)
    data.write_text(
        data.read_text(encoding="utf-8").replace("200.76", "999.99", 1), encoding="utf-8"
    )

    from datetime import UTC, datetime

    from goldbot.data.snapshot import write_manifest

    with pytest.raises(DataIntegrityError, match="different digest"):
        write_manifest(
            manifest_dir=tmp_path / "data" / "snapshots",
            data_path=data,
            symbol="GLD",
            cadence="daily",
            source="fixture",
            fetched_at=datetime(2026, 8, 21, 12, 0, tzinfo=UTC),
        )


def test_impossible_ohlc_is_refused_at_the_boundary(tmp_path: Path) -> None:
    """A bar whose low exceeds its high never becomes a Bar."""
    manifest = pin_fixture(tmp_path, fixture="gld_invalid_ohlc.csv")
    with pytest.raises(DataIntegrityError, match="low .* exceeds high"):
        load_bars(Path(manifest.data_path), "GLD")


def test_gaps_are_reported_not_interpolated(tmp_path: Path) -> None:
    from goldbot.data.feed import HistoricalFeed

    manifest = pin_fixture(tmp_path, fixture="gld_missing_sessions.csv")
    bars = load_bars(Path(manifest.data_path), "GLD")
    feed = HistoricalFeed(bars, digest=manifest.sha256)

    assert feed.gaps, "three removed sessions should surface as a gap"
    assert len(feed) == len(bars), "no bar was invented to fill the hole"
    assert "missing" in feed.gaps[0].describe()


def test_a_manifest_round_trips(tmp_path: Path) -> None:
    manifest = pin_fixture(tmp_path)
    path = tmp_path / "data" / "snapshots" / f"{manifest.snapshot_id}.manifest.json"
    assert Manifest.from_path(path) == manifest
