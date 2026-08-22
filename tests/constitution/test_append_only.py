"""Principle V: the audit trail cannot be edited.

FR-025 asks for an append-only record. Enforcing that in the method surface
would mean "append-only as long as everyone uses the wrapper". Enforcing it
with database triggers means append-only full stop, including from a sqlite3
shell someone opens at midnight.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from goldbot.journal.store import AuditStore
from tests.conftest import make_decision

pytestmark = pytest.mark.constitution

NOW = datetime(2026, 1, 5, 21, 0, tzinfo=UTC)

RECORD_TABLES = [
    "runs",
    "run_events",
    "decisions",
    "verdicts",
    "orders",
    "fills",
    "trades",
    "violations",
    "halts",
    "review_notes",
]


@pytest.fixture
def store(tmp_path: Path) -> AuditStore:
    """A store with at least one row in every record table.

    Seeding all of them matters: a BEFORE UPDATE trigger fires per row, so an
    empty table would pass this test while proving nothing.
    """
    store = AuditStore(tmp_path / "audit.db")
    store.start_run(
        run_id="run-1",
        mode="BACKTEST",
        symbol="GLD",
        snapshot_digest="abc123",
        config_version="cfg1",
        envelope_version="env1",
        code_version="test",
        started_at=NOW,
    )
    decision_id = make_decision().id
    store.record_decision("run-1", make_decision())

    conn = store.connection
    stamp = NOW.isoformat()
    conn.execute(
        "INSERT INTO orders (order_id, run_id, decision_id, envelope_version, side, shares, "
        "submitted_at, simulated) VALUES ('o1','run-1',?,'env1','BUY',25,?,1)",
        (decision_id, stamp),
    )
    conn.execute(
        "INSERT INTO fills (fill_id, order_id, decision_id, symbol, side, price, shares, "
        "filled_at, commission, spread_cost, slippage_cost, slippage_vs_intended) "
        "VALUES ('f1','o1',?,'GLD','BUY','200.00',25,?,'0','0.50','0.40','0.10')",
        (decision_id, stamp),
    )
    conn.execute(
        "INSERT INTO trades (trade_id, run_id, symbol, entry_fill_id, exit_fill_id, shares, "
        "opened_at, closed_at, exit_reason, planned_risk, result_currency, result_r, "
        "risk_overrun, classification, opening_decision_id, closing_decision_id) "
        "VALUES ('t1','run-1','GLD','f1','f1',25,?,?,'STOP','100.00','-100.00','-1.00','0',"
        "'CORRECT',?,?)",
        (stamp, stamp, decision_id, decision_id),
    )
    conn.execute(
        "INSERT INTO violations (run_id, at, kind, statement, detail_json) "
        "VALUES ('run-1',?,'ALLOW_LIST','SPY is not on the gold allow-list.','{}')",
        (stamp,),
    )
    conn.execute(
        "INSERT INTO halts (run_id, at, kind, statement) "
        "VALUES ('run-1',?,'DAILY_LOSS','Daily loss limit reached.')",
        (stamp,),
    )
    conn.execute(
        "INSERT INTO review_notes (run_id, trade_id, principle, expectation, outcome, "
        "supports_principle, commentary) VALUES "
        "('run-1','t1','trend-alignment','Expected continuation.','Stopped out.',0,'Noted.')"
    )
    conn.commit()
    return store


def test_every_record_table_refuses_update(store: AuditStore) -> None:
    present = set(store.iter_tables())
    for table in RECORD_TABLES:
        assert table in present, f"{table} is missing from the schema"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.connection.execute(f"UPDATE {table} SET rowid = rowid")


def test_every_record_table_refuses_delete(store: AuditStore) -> None:
    for table in RECORD_TABLES:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            store.connection.execute(f"DELETE FROM {table}")


def test_a_recorded_decision_survives_an_edit_attempt(store: AuditStore) -> None:
    decision = make_decision()
    original = store.decision(decision.id)
    assert original is not None

    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "UPDATE decisions SET explanation = 'rewritten history' WHERE decision_id = ?",
            (decision.id,),
        )

    after = store.decision(decision.id)
    assert after is not None
    assert after["explanation"] == original["explanation"]


def test_run_status_is_appended_not_mutated(store: AuditStore) -> None:
    """The design choice that keeps `runs` inside the append-only rule."""
    assert store.run_status("run-1") == "RUNNING"
    store.append_run_event("run-1", NOW, "COMPLETE", bars_evaluated=400)
    assert store.run_status("run-1") == "COMPLETE"

    history = list(store.connection.execute("SELECT status FROM run_events ORDER BY event_id"))
    assert [row["status"] for row in history] == ["RUNNING", "COMPLETE"], (
        "both states must remain visible; a status column would have erased the first"
    )


def test_the_schema_refuses_to_record_a_live_order(store: AuditStore) -> None:
    """The fourth independent guard on FR-024."""
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO orders (order_id, run_id, decision_id, envelope_version, side, "
            "shares, submitted_at, simulated) VALUES "
            "('o1','run-1',?,'env1','BUY',10,'2026-01-05T21:00:00+00:00', 0)",
            (make_decision().id,),
        )


def test_a_decision_without_an_explanation_is_refused_by_the_database(store: AuditStore) -> None:
    """Belt and braces: the type refuses it too, but so does the table."""
    with pytest.raises(sqlite3.IntegrityError):
        store.connection.execute(
            "INSERT INTO decisions (decision_id, run_id, as_of, symbol, action, explanation) "
            "VALUES ('d2','run-1','2026-01-06T21:00:00+00:00','GLD','HOLD','   ')"
        )
