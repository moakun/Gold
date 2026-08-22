"""Stooq end-of-day data.

The default source, chosen because it needs no API key: the whole daily path
runs with zero credentials, which means CI runs offline and there is nothing to
leak. It permits personal, non-commercial use, which is exactly this project's
scope.

Market *data* over plain HTTP is fine. An order-placing client is not — see
research.md R3. Nothing in this module can place a trade.
"""

from __future__ import annotations

from datetime import date

import httpx

from goldbot.domain.errors import DataIntegrityError

BASE_URL = "https://stooq.com/q/d/l/"
TIMEOUT = httpx.Timeout(30.0)


def stooq_symbol(symbol: str) -> str:
    """Stooq suffixes US listings with `.us`."""
    lowered = symbol.lower()
    return lowered if "." in lowered else f"{lowered}.us"


def fetch_daily(symbol: str, start: date, end: date) -> bytes:
    """Fetch daily OHLCV as raw CSV bytes.

    Returns bytes rather than parsed rows on purpose: the digest is taken over
    exactly what arrived, before anything interprets it.
    """
    params = {
        "s": stooq_symbol(symbol),
        "d1": start.strftime("%Y%m%d"),
        "d2": end.strftime("%Y%m%d"),
        "i": "d",
    }
    try:
        response = httpx.get(BASE_URL, params=params, timeout=TIMEOUT, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise DataIntegrityError(f"could not fetch {symbol} from Stooq: {exc}") from exc

    payload = response.content
    text = payload.decode("utf-8", errors="replace").strip()

    if not text or text.lower().startswith("no data"):
        raise DataIntegrityError(
            f"Stooq returned no data for {symbol} between {start} and {end}. "
            "Check the symbol, or that the range covers trading days."
        )
    if not text.splitlines()[0].lower().startswith("date"):
        raise DataIntegrityError(
            f"Stooq returned something that is not a CSV for {symbol}: {text[:120]!r}"
        )
    return payload
