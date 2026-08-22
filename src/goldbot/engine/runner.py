"""Assembling a run.

Thin on purpose: it wires the pieces together and writes the artifacts. All the
judgement lives in the loop, the gate, and the rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from goldbot.config import Config
from goldbot.domain.bar import Bar
from goldbot.execution.simulated import SimulatedBroker
from goldbot.journal import report as report_module
from goldbot.journal.render import markdown_journal
from goldbot.journal.store import AuditStore
from goldbot.engine.clock import Clock, LiveClock
from goldbot.engine.loop import DecisionLoop, RunResult
from goldbot.risk.gate import RiskGate


@dataclass(frozen=True)
class RunArtifacts:
    result: RunResult
    metrics: report_module.Metrics
    journal_path: Path
    report_path: Path
    run_id: str
    fingerprint: str


def execute(
    *,
    config: Config,
    bars: tuple[Bar, ...],
    snapshot_id: str,
    snapshot_digest: str | None,
    code_version: str,
    fingerprint: str,
    run_id: str,
    out_dir: Path,
    store: AuditStore,
    mode: str = "BACKTEST",
    kill_latch: Path | None = None,
    halt_resumes_next_session: bool = True,
    clock: Clock | None = None,
) -> RunArtifacts:
    # Audit stamps need real time, but only engine/clock.py is allowed to read
    # it. Injecting the clock keeps that rule literally true rather than
    # carving out an exemption for orchestration code.
    clock = clock or LiveClock()
    started = clock.now()
    store.start_run(
        run_id=run_id,
        mode=mode,
        symbol=config.symbol,
        snapshot_digest=snapshot_digest,
        config_version=config.version,
        envelope_version=config.envelope.version,
        code_version=code_version,
        started_at=started,
    )

    gate = RiskGate(
        allow_list=config.allow_list,
        envelope=config.envelope,
        kill_latch=kill_latch,
    )
    loop = DecisionLoop(
        config=config,
        bars=bars,
        gate=gate,
        broker=SimulatedBroker(config.instrument, run_id=run_id),
        run_id=run_id,
        store=store,
        halt_resumes_next_session=halt_resumes_next_session,
    )

    try:
        result = loop.run()
    except Exception:
        store.append_run_event(run_id, clock.now(), "ABORTED", note="unhandled error")
        raise

    # Rejections the gate accumulated are violations worth keeping: an empty
    # violations table across a long run means the guards were never exercised.
    for rejection in gate.rejections:
        store.record_violation(run_id, started, rejection)

    metrics = report_module.compute(
        trades=result.trades,
        equity_curve=result.equity_curve,
        starting_equity=result.starting_equity,
        ending_equity=result.ending_equity,
        expense_ratio=config.instrument.expense_ratio,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    journal_path = out_dir / "journal.md"
    journal_path.write_text(
        markdown_journal(
            fingerprint=fingerprint,
            symbol=config.symbol,
            decisions=result.decisions,
            trades=result.trades,
            snapshot_id=snapshot_id,
            config_version=config.version,
        ),
        encoding="utf-8",
    )
    report_path = out_dir / "report.txt"
    report_path.write_text(
        report_module.render(metrics, cadence=config.cadence) + "\n", encoding="utf-8"
    )

    status = "HALTED" if result.halts else "COMPLETE"
    store.append_run_event(
        run_id, clock.now(), status, bars_evaluated=result.bars_evaluated
    )

    return RunArtifacts(
        result=result,
        metrics=metrics,
        journal_path=journal_path,
        report_path=report_path,
        run_id=run_id,
        fingerprint=fingerprint,
    )
