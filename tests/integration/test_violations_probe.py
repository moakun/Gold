"""Proving the guards fire.

A risk control that has never been observed refusing anything has not been
tested. These two probes make the refusals happen on purpose, so the
`violations` table is populated by design rather than by accident.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from goldbot.config import load_config
from goldbot.data.snapshot import load_bars
from goldbot.domain.errors import GuardViolation
from goldbot.engine.runner import execute
from goldbot.journal.store import AuditStore
from tests.integration._helpers import pin_fixture

REPO = Path(__file__).resolve().parents[2]
ALLOWLIST_PROBE = REPO / "config" / "violations-probe.toml"
HALT_PROBE = REPO / "config" / "halt-probe.toml"


def test_the_allowlist_probe_refuses_a_non_gold_symbol() -> None:
    """Principle II, failing closed at the boundary."""
    config = load_config(ALLOWLIST_PROBE)
    assert config.symbol == "SPY"
    with pytest.raises(GuardViolation, match="not on the gold allow-list"):
        config.instrument


def test_the_allowlist_probe_exits_with_code_four() -> None:
    """Exit 4 means a guard fired — distinct from bad data (3) or a halt (5)."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "goldbot.cli.main",
            "backtest",
            "--snapshot",
            "anything",
            "--config",
            str(ALLOWLIST_PROBE),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO / "src")},
        check=False,
    )
    assert result.returncode == 4, (
        f"expected exit 4 (guard triggered), got {result.returncode}\n{result.stderr}"
    )


def test_the_halt_probe_trips_the_daily_loss_limit(tmp_path: Path) -> None:
    manifest = pin_fixture(tmp_path)
    config = load_config(HALT_PROBE)
    bars = load_bars(Path(manifest.data_path), config.symbol)

    with AuditStore(tmp_path / "audit.db") as store:
        artifacts = execute(
            config=config,
            bars=bars,
            snapshot_id=manifest.snapshot_id,
            snapshot_digest=manifest.sha256,
            code_version="test",
            fingerprint="print",
            run_id="halt-probe",
            out_dir=tmp_path / "out",
            store=store,
        )
        halts = store.halts_for_run("halt-probe")
        violations = store.violations_for_run("halt-probe")
        status = store.run_status("halt-probe")

    assert artifacts.result.halts, "a 0.1% daily limit should trip on the first loss"
    assert halts, "the halt must be recorded, not just acted on"
    assert status == "HALTED"
    assert violations, "entries refused while halted must appear as violations"
    assert any(v["kind"] == "DAILY_LOSS_HALT" for v in violations)


def test_every_recorded_violation_explains_itself(tmp_path: Path) -> None:
    """A refused trade is a teaching moment, not an error code."""
    manifest = pin_fixture(tmp_path)
    config = load_config(HALT_PROBE)
    bars = load_bars(Path(manifest.data_path), config.symbol)

    with AuditStore(tmp_path / "audit.db") as store:
        execute(
            config=config,
            bars=bars,
            snapshot_id=manifest.snapshot_id,
            snapshot_digest=manifest.sha256,
            code_version="test",
            fingerprint="print",
            run_id="halt-probe",
            out_dir=tmp_path / "out",
            store=store,
        )
        violations = store.violations_for_run("halt-probe")

    for violation in violations:
        assert len(violation["statement"].split()) >= 8, (
            f"terse violation statement: {violation['statement']!r}"
        )
        assert violation["kind"].isupper()


def test_a_halted_run_still_explains_every_bar(tmp_path: Path) -> None:
    """Halting stops trading, not journalling. Those days had reasoning too."""
    manifest = pin_fixture(tmp_path)
    config = load_config(HALT_PROBE)
    bars = load_bars(Path(manifest.data_path), config.symbol)

    with AuditStore(tmp_path / "audit.db") as store:
        artifacts = execute(
            config=config,
            bars=bars,
            snapshot_id=manifest.snapshot_id,
            snapshot_digest=manifest.sha256,
            code_version="test",
            fingerprint="print",
            run_id="halt-probe",
            out_dir=tmp_path / "out",
            store=store,
        )

    assert len(artifacts.result.decisions) == len(bars)
    for decision in artifacts.result.decisions:
        assert decision.explanation.strip()


def test_an_oversized_risk_request_is_refused_by_the_gate(tmp_path: Path) -> None:
    """Sizing normally respects the envelope, so this forces the gate's own check."""
    from datetime import UTC, datetime

    from goldbot.domain.envelope import RiskEnvelope
    from goldbot.domain.money import dec
    from goldbot.domain.verdict import Rejection
    from goldbot.risk.gate import RiskGate
    from tests.conftest import make_account, make_decision, make_plan

    config = load_config(HALT_PROBE)
    tight = replace(config, envelope=RiskEnvelope(max_risk_per_trade=dec("0.001")))
    gate = RiskGate(allow_list=tight.allow_list, envelope=tight.envelope)

    outcome = gate.authorize(
        make_decision(plan=make_plan(risk_pct="0.050")),
        make_account(),
        now=datetime(2026, 1, 5, 21, 0, tzinfo=UTC),
    )
    assert isinstance(outcome, Rejection)
    assert outcome.kind == "RISK_EXCEEDED"
