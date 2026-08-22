"""SC-004: the same inputs produce the same journal, byte for byte.

When this fails it is nearly always one of three things: a wall-clock read in
the decision path, a float where a Decimal should be, or iteration over
something unordered. All three are guarded elsewhere; this is the test that
notices when a guard has a hole.
"""

from __future__ import annotations

from pathlib import Path

from tests.integration._helpers import run_backtest


def test_two_runs_produce_identical_journals(tmp_path: Path) -> None:
    first, _ = run_backtest(tmp_path / "a", run_id="run-a", out_name="a")
    second, _ = run_backtest(tmp_path / "b", run_id="run-b", out_name="b")

    assert first.journal_path.read_text(encoding="utf-8") == second.journal_path.read_text(
        encoding="utf-8"
    )


def test_two_runs_produce_identical_reports(tmp_path: Path) -> None:
    first, _ = run_backtest(tmp_path / "a", run_id="run-a", out_name="a")
    second, _ = run_backtest(tmp_path / "b", run_id="run-b", out_name="b")

    assert first.report_path.read_text(encoding="utf-8") == second.report_path.read_text(
        encoding="utf-8"
    )


def test_two_runs_agree_on_every_trade(tmp_path: Path) -> None:
    first, _ = run_backtest(tmp_path / "a", run_id="run-a", out_name="a")
    second, _ = run_backtest(tmp_path / "b", run_id="run-b", out_name="b")

    assert len(first.result.trades) == len(second.result.trades)
    for a, b in zip(first.result.trades, second.result.trades, strict=True):
        assert a.result_currency == b.result_currency
        assert a.result_r == b.result_r
        assert a.exit_reason == b.exit_reason


def test_the_snapshot_digest_is_stable(tmp_path: Path) -> None:
    _, first = run_backtest(tmp_path / "a", run_id="run-a", out_name="a")
    _, second = run_backtest(tmp_path / "b", run_id="run-b", out_name="b")
    assert first.sha256 == second.sha256


def test_a_changed_config_changes_the_result(tmp_path: Path) -> None:
    """The negative control: reproducibility must not mean insensitivity."""
    from dataclasses import replace

    from tests.integration._helpers import load_baseline_raw

    baseline = load_baseline_raw()
    tweaked = replace(baseline, strategy=replace(baseline.strategy, momentum_lookback=5))

    first, _ = run_backtest(tmp_path / "a", run_id="run-a", out_name="a")
    second, _ = run_backtest(tmp_path / "b", config=tweaked, run_id="run-b", out_name="b")

    assert first.journal_path.read_text(encoding="utf-8") != second.journal_path.read_text(
        encoding="utf-8"
    )
