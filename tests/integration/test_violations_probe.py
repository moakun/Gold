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


def _run_halt_probe(tmp_path: Path, *, sticky: bool):  # type: ignore[no-untyped-def]
    """Run the hair-trigger config over the gap fixture.

    `sticky=True` is paper semantics: the halt requires an explicit resume.
    `sticky=False` is backtest semantics: it lifts at the next session, which
    stands in for the operator returning the following morning (T072).
    """
    manifest = pin_fixture(tmp_path, fixture="gld_gap_stop.csv")
    config = load_config(HALT_PROBE)
    bars = load_bars(Path(manifest.data_path), config.symbol)

    store = AuditStore(tmp_path / "audit.db")
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
        halt_resumes_next_session=not sticky,
    )
    return artifacts, store


def test_the_halt_probe_trips_the_daily_loss_limit(tmp_path: Path) -> None:
    artifacts, store = _run_halt_probe(tmp_path, sticky=False)
    try:
        assert artifacts.result.halts, "a gap 20x the planned risk must trip a 0.1% daily limit"
        assert store.halts_for_run("halt-probe"), "the halt must be recorded, not just acted on"
        assert store.run_status("halt-probe") == "HALTED"
    finally:
        store.close()


def test_the_gap_through_the_stop_is_recorded_as_a_risk_overrun(tmp_path: Path) -> None:
    """The whole reason this fixture exists: stops are intentions, not guarantees."""
    from goldbot.domain.position import ExitReason

    artifacts, store = _run_halt_probe(tmp_path, sticky=False)
    try:
        gapped = [
            t for t in artifacts.result.trades if t.exit_reason is ExitReason.GAP_THROUGH_STOP
        ]
        assert gapped, "the fixture gaps 30 points below the stop; that must show up as one"
        trade = gapped[0]
        assert trade.risk_overrun > 0
        assert trade.result_r < -5, "a 30-point gap on a ~1.5-point stop is far worse than -1R"
        assert artifacts.metrics.risk_overrun_count >= 1
        assert "Trades over plan" in artifacts.report_path.read_text(encoding="utf-8")
    finally:
        store.close()


def test_a_sticky_halt_refuses_every_later_entry(tmp_path: Path) -> None:
    """Paper semantics: the halt does not clear itself overnight (FR-014)."""
    artifacts, store = _run_halt_probe(tmp_path, sticky=True)
    try:
        violations = store.violations_for_run("halt-probe")
        assert violations, "entries refused while halted must appear as violations"
        assert {v["kind"] for v in violations} == {"HALTED"}
        assert len(artifacts.result.trades) == 1, (
            "only the trade that caused the halt should exist; the rest were refused"
        )
    finally:
        store.close()


def test_a_resuming_halt_lets_the_run_continue(tmp_path: Path) -> None:
    """Backtest semantics, and the contrast that makes the difference visible."""
    artifacts, store = _run_halt_probe(tmp_path, sticky=False)
    try:
        assert len(artifacts.result.trades) > 1, (
            "with the halt lifting each session the run should continue trading"
        )
        assert not store.violations_for_run("halt-probe")
    finally:
        store.close()


def test_every_recorded_violation_explains_itself(tmp_path: Path) -> None:
    """A refused trade is a teaching moment, not an error code."""
    _, store = _run_halt_probe(tmp_path, sticky=True)
    try:
        violations = store.violations_for_run("halt-probe")
        assert violations
        for violation in violations:
            assert len(violation["statement"].split()) >= 8, (
                f"terse violation statement: {violation['statement']!r}"
            )
            assert violation["kind"].isupper()
    finally:
        store.close()


def test_a_halted_run_still_explains_every_bar(tmp_path: Path) -> None:
    """Halting stops trading, not journalling. Those days had reasoning too."""
    artifacts, store = _run_halt_probe(tmp_path, sticky=True)
    try:
        assert len(artifacts.result.decisions) == artifacts.result.bars_evaluated
        for decision in artifacts.result.decisions:
            assert decision.explanation.strip()
    finally:
        store.close()


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
