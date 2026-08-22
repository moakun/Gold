"""FR-001: every evaluated bar produces an explained decision.

The days the system did nothing are the majority of days, and they are the ones
a trading journal normally omits. Omitting them is how you end up unable to
answer "why didn't it buy in March?".
"""

from __future__ import annotations

from pathlib import Path

from goldbot.domain.decision import Action
from tests.integration._helpers import run_backtest


def test_one_decision_per_evaluated_bar(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    result = artifacts.result
    assert len(result.decisions) == result.bars_evaluated == 400


def test_every_decision_carries_verdicts_and_prose(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    for decision in artifacts.result.decisions:
        assert decision.verdicts, f"{decision.as_of} has no verdicts"
        assert decision.explanation.strip(), f"{decision.as_of} has no explanation"
        assert len(decision.explanation.split()) > 5, f"{decision.as_of} explanation is a stub"


def test_every_skip_names_the_condition_that_vetoed_it(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    skips = [d for d in artifacts.result.decisions if d.action is Action.SKIP]
    assert skips, "the fixture should produce skips"
    for decision in skips:
        assert decision.blocking_verdict is not None
        assert not decision.blocking_verdict.passed
        assert decision.blocking_verdict.statement in decision.explanation


def test_every_entry_states_stop_size_risk_and_reward(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    entries = [d for d in artifacts.result.decisions if d.action is Action.ENTER]
    assert entries, "the fixture should produce entries"
    for decision in entries:
        plan = decision.plan
        assert plan is not None
        assert plan.stop < plan.intended_entry
        assert plan.shares >= 1
        assert plan.risk_pct > 0
        assert f"{plan.stop:.2f}" in decision.explanation
        assert f"{plan.shares}" in decision.explanation


def test_skips_report_what_passed_as_well_as_what_failed(tmp_path: Path) -> None:
    """Rules do not short-circuit, so a skip shows the whole picture."""
    artifacts, _ = run_backtest(tmp_path)
    near_misses = [
        d
        for d in artifacts.result.decisions
        if d.action is Action.SKIP and len(d.failed_verdicts()) == 1
    ]
    assert near_misses, "some days should fail on exactly one condition"
    sample = near_misses[0]
    assert sample.passed_verdicts()
    assert "near miss" in sample.explanation


def test_a_setup_that_was_nowhere_near_is_not_called_a_near_miss(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    far = [
        d
        for d in artifacts.result.decisions
        if d.action is Action.SKIP and len(d.failed_verdicts()) > 1
    ]
    assert far
    assert "near miss" not in far[0].explanation
    assert "not close" in far[0].explanation


def test_the_journal_file_contains_every_bar(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    journal = artifacts.journal_path.read_text(encoding="utf-8")
    headings = journal.count("\n## ")
    assert headings == 400, f"journal has {headings} day entries, expected 400"


def test_risk_never_exceeded_the_envelope_across_the_whole_run(tmp_path: Path) -> None:
    artifacts, _ = run_backtest(tmp_path)
    limit = artifacts.result.decisions[0]  # placeholder to keep the import honest
    assert limit is not None
    from tests.integration._helpers import load_baseline_raw

    envelope = load_baseline_raw().envelope
    for decision in artifacts.result.decisions:
        if decision.plan is not None:
            assert decision.plan.risk_pct <= envelope.max_risk_per_trade
