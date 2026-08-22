"""Principle V, reproducibility: the decision path may not read the system clock.

A wall-clock read is the classic source of a backtest that will not reproduce.
Time is injected through `Clock`, and the only module allowed to ask the
operating system what time it is is the live clock implementation.
"""

from __future__ import annotations

import pytest

from tests.constitution._scan import attribute_chains, imported_names, modules_in, rel

pytestmark = pytest.mark.constitution

FORBIDDEN_CHAINS = {
    "datetime.now",
    "datetime.today",
    "datetime.utcnow",
    "datetime.datetime.now",
    "datetime.datetime.today",
    "datetime.datetime.utcnow",
    "date.today",
    "time.time",
    "time.monotonic",
}

#: The live clock is the one place allowed to read real time — that is its job.
#: Timing the kill switch also needs a real elapsed measurement.
EXEMPT = {"engine/clock.py", "risk/kill_switch.py"}


def _check(package: str) -> list[str]:
    offenders: list[str] = []
    for path in modules_in(package):
        if any(rel(path).endswith(exempt) for exempt in EXEMPT):
            continue
        chains = attribute_chains(path)
        for chain in sorted(chains & FORBIDDEN_CHAINS):
            offenders.append(f"{rel(path)} calls {chain}")
    return offenders


def test_strategy_never_reads_the_clock() -> None:
    offenders = _check("strategy")
    assert not offenders, "strategy/ must take time from the injected clock:\n" + "\n".join(
        offenders
    )


def test_risk_never_reads_the_clock() -> None:
    offenders = _check("risk")
    assert not offenders, "risk/ must take time from the injected clock:\n" + "\n".join(offenders)


def test_engine_reads_the_clock_only_in_the_clock_module() -> None:
    offenders = _check("engine")
    assert not offenders, (
        "only engine/clock.py may read real time; everything else receives it:\n"
        + "\n".join(offenders)
    )


def test_strategy_does_not_import_time_modules_directly() -> None:
    offenders: list[str] = []
    for path in modules_in("strategy"):
        names = imported_names(path)
        if "time" in names:
            offenders.append(f"{rel(path)} imports time")
    assert not offenders, "\n".join(offenders)
