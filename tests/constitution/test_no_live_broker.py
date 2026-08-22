"""FR-024: no live execution path exists.

The spec does not say "live trading is disabled". It says no path capable of
reaching a live brokerage account may exist — because a disabled flag is one
edit away from enabled, and an absent dependency is not.

This is checked in four independent places. Any one of them failing means the
guarantee has quietly weakened:

  1. no brokerage trading SDK in the lockfile           (here)
  2. exactly one Broker implementation, the simulator   (here)
  3. no network I/O reachable from execution/           (test_no_network_in_execution)
  4. CHECK (simulated = 1) in the audit schema          (test_append_only)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.constitution._scan import REPO, imported_names, modules_in, rel

pytestmark = pytest.mark.constitution

#: Packages that can place a real order. Not an exhaustive list of every broker
#: on earth — it is the set a developer on this project might plausibly reach
#: for, which is what a guard needs to cover.
TRADING_SDKS = (
    "alpaca-py",
    "alpaca-trade-api",
    "ib-insync",
    "ibapi",
    "ib-async",
    "ccxt",
    "oandapyv20",
    "tda-api",
    "schwab-py",
    "robin-stocks",
    "python-binance",
    "polygon-api-client",
    "tastytrade",
    "questrade-api",
)


def test_no_brokerage_trading_sdk_in_the_lockfile() -> None:
    lock = REPO / "uv.lock"
    assert lock.exists(), "uv.lock must be committed — pinned deps are part of reproducibility"
    content = lock.read_text(encoding="utf-8").lower()

    found = [sdk for sdk in TRADING_SDKS if f'name = "{sdk}"' in content]
    assert not found, (
        f"a brokerage trading SDK is installed: {found}. This version has no live "
        "execution path (FR-024). Market *data* may come from a vendor over plain HTTP; "
        "an order-placing client may not be present at all."
    )


def test_simulated_broker_is_the_only_implementation() -> None:
    execution_modules = modules_in("execution")
    assert execution_modules, "execution/ should contain the simulated broker"

    names = {p.stem for p in execution_modules}
    assert names == {"simulated"}, (
        f"execution/ contains {sorted(names)}; the only permitted implementation in this "
        "version is the simulator"
    )


def test_execution_imports_no_http_client() -> None:
    network = {"httpx", "requests", "urllib", "urllib3", "http", "socket", "aiohttp", "websockets"}
    offenders: list[str] = []
    for path in modules_in("execution"):
        for name in sorted(imported_names(path) & network):
            offenders.append(f"{rel(path)} imports {name}")
    assert not offenders, "execution/ must not be able to talk to anything:\n" + "\n".join(
        offenders
    )


def test_no_source_file_mentions_a_live_trading_endpoint() -> None:
    """Catches a base URL pasted in as a convenience."""
    markers = ("api.alpaca.markets", "paper-api.alpaca.markets", "/v2/orders", "brokerapi")
    offenders: list[str] = []
    for path in Path(REPO / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for marker in markers:
            if marker in text:
                offenders.append(f"{rel(path)} mentions {marker}")
    assert not offenders, "\n".join(offenders)
