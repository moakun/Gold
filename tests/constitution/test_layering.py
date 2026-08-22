"""The dependency direction the architecture rests on.

`domain/` imports nothing from the other layers. That is what lets the rest of
these constitution tests be cheap: if the value types depended on the data
layer, "no network in the decision path" would be unanswerable.
"""

from __future__ import annotations

import pytest

from tests.constitution._scan import imported_names, modules_in, rel

pytestmark = pytest.mark.constitution

OTHER_LAYERS = ("data", "strategy", "risk", "execution", "engine", "journal", "lessons", "cli")


def test_domain_depends_on_no_other_layer() -> None:
    offenders: list[str] = []
    for path in modules_in("domain"):
        for name in imported_names(path):
            for layer in OTHER_LAYERS:
                if name.startswith(f"goldbot.{layer}"):
                    offenders.append(f"{rel(path)} imports {name}")
    assert not offenders, "domain/ must not depend on any other layer:\n" + "\n".join(offenders)


def test_strategy_depends_only_on_domain() -> None:
    forbidden = ("data", "execution", "engine", "journal", "cli", "risk")
    offenders: list[str] = []
    for path in modules_in("strategy"):
        for name in imported_names(path):
            for layer in forbidden:
                if name.startswith(f"goldbot.{layer}"):
                    offenders.append(f"{rel(path)} imports {name}")
    assert not offenders, "strategy/ may only depend on domain/:\n" + "\n".join(offenders)


def test_risk_depends_only_on_domain() -> None:
    forbidden = ("data", "strategy", "execution", "journal", "cli")
    offenders: list[str] = []
    for path in modules_in("risk"):
        for name in imported_names(path):
            for layer in forbidden:
                if name.startswith(f"goldbot.{layer}"):
                    offenders.append(f"{rel(path)} imports {name}")
    assert not offenders, "risk/ may only depend on domain/:\n" + "\n".join(offenders)
