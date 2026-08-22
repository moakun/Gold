"""Generate the committed CSV fixtures.

Run with `python tests/fixtures/make_fixtures.py`. Output is deterministic — a
tiny linear congruential generator stands in for market noise so the fixtures
are byte-identical on every machine and every rerun. No `random` module, on
purpose: the reproducibility tests would be meaningless if the data underneath
them wandered.

The long fixture deliberately contains all four situations the system has to
handle honestly:

    bars   0-119   a clean uptrend      (entries should trigger)
    bars 120-199   choppy sideways      (the filter should veto most days)
    bars 200-259   a sharp drawdown, including one overnight gap down through
                   any plausible stop  (proves stops are intentions)
    bars 260-399   recovery
"""

from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).parent


class Noise:
    """A minimal LCG. Deterministic, portable, and obviously not cryptographic."""

    def __init__(self, seed: int) -> None:
        self.state = seed

    def next(self) -> float:
        self.state = (self.state * 1103515245 + 12345) % (2**31)
        return self.state / (2**31)

    def signed(self, scale: float) -> float:
        return (self.next() - 0.5) * 2 * scale


def sessions(start: date, count: int) -> list[date]:
    """Weekdays only. Good enough for fixtures; the real feed uses a calendar."""
    out: list[date] = []
    day = start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return out


def q(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")


def build_rows(count: int = 400) -> list[dict[str, str]]:
    noise = Noise(seed=20260821)
    days = sessions(date(2024, 1, 2), count)
    rows: list[dict[str, str]] = []
    close = 200.00

    for i, day in enumerate(days):
        if i < 120:
            drift = 0.22
        elif i < 200:
            drift = 0.01
        elif i < 260:
            drift = -0.38
        else:
            drift = 0.18

        gap = 0.0
        if i == 231:
            # The overnight gap: opens well below the prior close, straight
            # through any stop a sane rule would have placed.
            gap = -7.40

        open_ = close + gap + noise.signed(0.35)
        close = open_ + drift + noise.signed(1.10)
        high = max(open_, close) + abs(noise.signed(0.85))
        low = min(open_, close) - abs(noise.signed(0.85))
        volume = 4_000_000 + int(noise.next() * 3_000_000)
        if i == 231:
            volume *= 3

        rows.append(
            {
                "Date": day.isoformat(),
                "Open": str(q(open_)),
                "High": str(q(high)),
                "Low": str(q(low)),
                "Close": str(q(close)),
                "Volume": str(volume),
            }
        )
    return rows


def write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Date", "Open", "High", "Low", "Close", "Volume"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.name}: {len(rows)} rows")


def main() -> None:
    rows = build_rows()

    write(HERE / "gld_daily.csv", rows)
    write(HERE / "gld_tiny.csv", rows[:30])

    # Same data with three consecutive sessions removed, so the feed's gap
    # detection has something to find.
    gapped = rows[:150] + rows[153:]
    write(HERE / "gld_missing_sessions.csv", gapped)

    # A bar whose low is above its high. The loader must refuse this outright.
    broken = [dict(r) for r in rows[:20]]
    broken[10]["Low"] = str(Decimal(broken[10]["High"]) + Decimal("5.00"))
    write(HERE / "gld_invalid_ohlc.csv", broken)


if __name__ == "__main__":
    main()
