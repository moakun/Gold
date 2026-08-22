"""Principle III and IV: rules are pure functions of what they can see.

A rule that reads a file, calls an API, or rolls a die is a rule whose verdict
cannot be reproduced — and an unreproducible verdict is an unexplainable one,
because "why did it do that?" has no stable answer.
"""

from __future__ import annotations

import pytest

from tests.constitution._scan import called_names, imported_names, modules_in, rel

pytestmark = pytest.mark.constitution

FORBIDDEN_IMPORTS = {
    "random",
    "secrets",
    "httpx",
    "requests",
    "urllib",
    "urllib3",
    "socket",
    "aiohttp",
    "sqlite3",
    "subprocess",
    "os",
    "numpy.random",
}

FORBIDDEN_CALLS = {"open", "input", "print", "eval", "exec"}


def test_strategy_imports_nothing_impure() -> None:
    offenders: list[str] = []
    for path in modules_in("strategy"):
        for name in sorted(imported_names(path) & FORBIDDEN_IMPORTS):
            offenders.append(f"{rel(path)} imports {name}")
    assert not offenders, (
        "rules must be pure functions of the MarketView they are handed:\n" + "\n".join(offenders)
    )


def test_strategy_performs_no_io_calls() -> None:
    offenders: list[str] = []
    for path in modules_in("strategy"):
        for name in sorted(called_names(path) & FORBIDDEN_CALLS):
            offenders.append(f"{rel(path)} calls {name}()")
    assert not offenders, "\n".join(offenders)


def test_risk_layer_is_equally_pure() -> None:
    """The risk gate decides; it does not fetch, print, or persist."""
    allowed_exceptions = {"risk/kill_switch.py"}  # the latch is a file by design
    offenders: list[str] = []
    for path in modules_in("risk"):
        if any(rel(path).endswith(x) for x in allowed_exceptions):
            continue
        for name in sorted(imported_names(path) & FORBIDDEN_IMPORTS):
            offenders.append(f"{rel(path)} imports {name}")
        for name in sorted(called_names(path) & FORBIDDEN_CALLS):
            offenders.append(f"{rel(path)} calls {name}()")
    assert not offenders, "\n".join(offenders)


def test_no_randomness_anywhere_in_the_decision_path() -> None:
    """Not seeded — absent. A seed is a thing someone can change."""
    offenders: list[str] = []
    for package in ("domain", "strategy", "risk", "engine", "execution"):
        for path in modules_in(package):
            names = imported_names(path)
            if "random" in names or "numpy.random" in names or "secrets" in names:
                offenders.append(rel(path))
    assert not offenders, "randomness in the decision path:\n" + "\n".join(offenders)
