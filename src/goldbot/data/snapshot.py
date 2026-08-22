"""Pinned data snapshots.

A backtest is only reproducible if the data underneath it cannot move. The bulk
CSV is hashed, the hash goes in a manifest, and the manifest is verified before
every run. A digest mismatch stops the run — that failure is the feature, not
an inconvenience.

Manifests are tracked in git; the bulk data they describe is not.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from goldbot.domain.bar import Bar
from goldbot.domain.errors import DataIntegrityError
from goldbot.domain.money import dec

#: Regular US equity session. zoneinfo handles the daylight-saving shift, which
#: a fixed UTC offset would silently get wrong for half the year.
EXCHANGE_TZ = ZoneInfo("America/New_York")
SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)

EXPECTED_HEADER = ["Date", "Open", "High", "Low", "Close", "Volume"]


@dataclass(frozen=True, slots=True)
class Manifest:
    """What makes a snapshot citable: where it came from and exactly what it contains."""

    snapshot_id: str
    symbol: str
    cadence: str
    source: str
    fetched_at: str
    range_from: str
    range_to: str
    row_count: int
    sha256: str
    data_path: str
    notes: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_path(cls, path: Path) -> Manifest:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise DataIntegrityError(f"manifest {path.name} is not valid JSON: {exc}") from exc
        try:
            return cls(**payload)
        except TypeError as exc:
            raise DataIntegrityError(f"manifest {path.name} has unexpected fields: {exc}") from exc


def digest_of(path: Path) -> str:
    """SHA-256 over the raw bytes as fetched, before any parsing."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def session_bounds(day: date) -> tuple[datetime, datetime]:
    """The UTC start and end of one regular session."""
    start = datetime.combine(day, SESSION_OPEN, tzinfo=EXCHANGE_TZ)
    end = datetime.combine(day, SESSION_CLOSE, tzinfo=EXCHANGE_TZ)
    return start.astimezone(ZoneInfo("UTC")), end.astimezone(ZoneInfo("UTC"))


def write_manifest(
    *,
    manifest_dir: Path,
    data_path: Path,
    symbol: str,
    cadence: str,
    source: str,
    fetched_at: datetime,
    notes: str = "",
) -> Manifest:
    """Hash the data and describe it.

    Never rewrites an existing manifest whose digest differs — a changed
    upstream produces a new snapshot id, so old backtests stay reproducible.
    """
    rows = list(read_rows(data_path))
    if not rows:
        raise DataIntegrityError(f"{data_path.name} contains no rows")

    first, last = rows[0]["Date"], rows[-1]["Date"]
    snapshot_id = f"{symbol.upper()}-{cadence}-{first}-{last}"
    manifest = Manifest(
        snapshot_id=snapshot_id,
        symbol=symbol.upper(),
        cadence=cadence,
        source=source,
        fetched_at=fetched_at.isoformat(),
        range_from=first,
        range_to=last,
        row_count=len(rows),
        sha256=digest_of(data_path),
        data_path=str(data_path).replace("\\", "/"),
        notes=notes,
    )

    manifest_dir.mkdir(parents=True, exist_ok=True)
    target = manifest_dir / f"{snapshot_id}.manifest.json"
    if target.exists():
        existing = Manifest.from_path(target)
        if existing.sha256 != manifest.sha256:
            raise DataIntegrityError(
                f"a snapshot named {snapshot_id} already exists with a different digest.\n"
                f"  existing: {existing.sha256[:16]}...\n"
                f"  new:      {manifest.sha256[:16]}...\n"
                "The upstream data changed. Fetch under a new range so the old backtest "
                "stays reproducible rather than silently replacing its inputs."
            )
    target.write_text(manifest.to_json(), encoding="utf-8")
    return manifest


def find_manifest(manifest_dir: Path, snapshot_id: str) -> Manifest:
    path = manifest_dir / f"{snapshot_id}.manifest.json"
    if not path.exists():
        available = sorted(p.name.replace(".manifest.json", "") for p in manifest_dir.glob("*.manifest.json"))
        raise DataIntegrityError(
            f"no snapshot {snapshot_id!r}. Available: {available or 'none — run `goldbot data pull` first'}"
        )
    return Manifest.from_path(path)


def verify(manifest: Manifest, *, root: Path) -> None:
    """Refuse to proceed on a digest mismatch."""
    data_path = root / manifest.data_path
    if not data_path.exists():
        raise DataIntegrityError(
            f"snapshot {manifest.snapshot_id} references {manifest.data_path}, which is missing. "
            "Bulk data is gitignored — re-run `goldbot data pull` to restore it."
        )
    actual = digest_of(data_path)
    if actual != manifest.sha256:
        raise DataIntegrityError(
            f"snapshot {manifest.snapshot_id} does not match its manifest.\n"
            f"  expected: {manifest.sha256}\n"
            f"  actual:   {actual}\n"
            "The data has changed since it was pinned. Any backtest run against it would "
            "not be the backtest the manifest describes."
        )


def read_rows(path: Path) -> list[dict[str, str]]:
    """Parse the CSV, checking the header rather than trusting column order."""
    with path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [c for c in EXPECTED_HEADER if c not in header]
        if missing:
            raise DataIntegrityError(
                f"{path.name} is missing column(s) {missing}; found {header}"
            )
        return list(reader)


def load_bars(path: Path, symbol: str) -> tuple[Bar, ...]:
    """Turn a CSV into immutable bars, refusing anything impossible.

    This is the boundary. Past it, the engine sees only frozen `Bar` objects
    and exact decimals.
    """
    bars: list[Bar] = []
    previous_end: datetime | None = None

    for line_no, row in enumerate(read_rows(path), start=2):
        try:
            day = date.fromisoformat(row["Date"].strip())
        except ValueError as exc:
            raise DataIntegrityError(f"{path.name} line {line_no}: bad date {row['Date']!r}") from exc

        start, end = session_bounds(day)
        if previous_end is not None and end <= previous_end:
            raise DataIntegrityError(
                f"{path.name} line {line_no}: bar at {day} is not after the previous bar. "
                "Rows must be in ascending order with no duplicates."
            )

        try:
            bar = Bar(
                symbol=symbol.upper(),
                start=start,
                end=end,
                open=dec(row["Open"].strip()),
                high=dec(row["High"].strip()),
                low=dec(row["Low"].strip()),
                close=dec(row["Close"].strip()),
                volume=int(row["Volume"].strip() or 0),
            )
        except DataIntegrityError as exc:
            raise DataIntegrityError(f"{path.name} line {line_no}: {exc}") from exc
        except (ValueError, ArithmeticError) as exc:
            raise DataIntegrityError(f"{path.name} line {line_no}: unparseable row — {exc}") from exc

        bars.append(bar)
        previous_end = end

    if not bars:
        raise DataIntegrityError(f"{path.name} produced no bars")
    return tuple(bars)
