"""The append-only audit store.

Writes happen *before* the action they describe, never after. A crash between
recording a decision and executing it leaves a decision with no fill, which is
recoverable and honest. The reverse would leave a trade nobody can explain.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from goldbot.domain.decision import Decision
from goldbot.domain.order import Fill, Order
from goldbot.domain.position import Trade
from goldbot.domain.verdict import Rejection

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _json(payload: Mapping[str, Any]) -> str:
    """Serialise evidence, keeping decimals exact by writing them as strings."""
    return json.dumps(
        {k: (str(v) if isinstance(v, Decimal) else v) for k, v in payload.items()},
        sort_keys=True,
        ensure_ascii=False,
    )


def _iso(moment: datetime) -> str:
    return moment.isoformat()


class AuditStore:
    """One SQLite file. Append-only by construction, not by convention."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        self._conn.commit()

    def close(self) -> None:
        self._conn.commit()
        self._conn.close()

    def __enter__(self) -> AuditStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- writers ----------------------------------------------------------

    def start_run(
        self,
        *,
        run_id: str,
        mode: str,
        symbol: str,
        snapshot_digest: str | None,
        config_version: str,
        envelope_version: str,
        code_version: str,
        started_at: datetime,
    ) -> str:
        self._conn.execute(
            "INSERT INTO runs (run_id, mode, symbol, snapshot_digest, config_version, "
            "envelope_version, code_version, started_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                run_id,
                mode,
                symbol,
                snapshot_digest,
                config_version,
                envelope_version,
                code_version,
                _iso(started_at),
            ),
        )
        self.append_run_event(run_id, started_at, "RUNNING")
        self._conn.commit()
        return run_id

    def append_run_event(
        self,
        run_id: str,
        at: datetime,
        status: str,
        bars_evaluated: int = 0,
        note: str = "",
    ) -> None:
        self._conn.execute(
            "INSERT INTO run_events (run_id, at, status, bars_evaluated, note) VALUES (?,?,?,?,?)",
            (run_id, _iso(at), status, bars_evaluated, note),
        )
        self._conn.commit()

    def record_decision(self, run_id: str, decision: Decision) -> None:
        plan_json = None
        if decision.plan is not None:
            plan = decision.plan
            plan_json = _json(
                {
                    "intended_entry": plan.intended_entry,
                    "stop": plan.stop,
                    "target": plan.target,
                    "shares": plan.shares,
                    "risk_amount": plan.risk_amount,
                    "risk_pct": plan.risk_pct,
                    "reward_risk": plan.reward_risk,
                    "binding_constraint": plan.binding_constraint.value,
                }
            )
        self._conn.execute(
            "INSERT INTO decisions (decision_id, run_id, as_of, symbol, action, explanation, "
            "blocking_rule_id, plan_json) VALUES (?,?,?,?,?,?,?,?)",
            (
                decision.id,
                run_id,
                _iso(decision.as_of),
                decision.symbol,
                decision.action.value,
                decision.explanation,
                decision.blocking_verdict.rule_id if decision.blocking_verdict else None,
                plan_json,
            ),
        )
        self._conn.executemany(
            "INSERT INTO verdicts (decision_id, ordinal, rule_id, principle, passed, "
            "evidence_json, statement) VALUES (?,?,?,?,?,?,?)",
            [
                (
                    decision.id,
                    ordinal,
                    verdict.rule_id,
                    verdict.principle,
                    1 if verdict.passed else 0,
                    _json(verdict.evidence),
                    verdict.statement,
                )
                for ordinal, verdict in enumerate(decision.verdicts)
            ],
        )
        self._conn.commit()

    def record_order(self, run_id: str, order: Order) -> None:
        self._conn.execute(
            "INSERT INTO orders (order_id, run_id, decision_id, envelope_version, side, "
            "shares, submitted_at, simulated) VALUES (?,?,?,?,?,?,?,1)",
            (
                order.id,
                run_id,
                order.decision_id,
                order.authorization.envelope_version,
                order.side.value,
                order.shares,
                _iso(order.submitted_at),
            ),
        )
        self._conn.commit()

    def record_fill(self, fill: Fill, fill_id: str) -> None:
        self._conn.execute(
            "INSERT INTO fills (fill_id, order_id, decision_id, symbol, side, price, shares, "
            "filled_at, commission, spread_cost, slippage_cost, slippage_vs_intended) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                fill_id,
                fill.order_id,
                fill.decision_id,
                fill.symbol,
                fill.side.value,
                str(fill.price),
                fill.shares,
                _iso(fill.at),
                str(fill.costs.commission),
                str(fill.costs.spread),
                str(fill.costs.slippage),
                str(fill.slippage_vs_intended),
            ),
        )
        self._conn.commit()

    def record_trade(
        self, run_id: str, trade: Trade, trade_id: str, entry_fill_id: str, exit_fill_id: str
    ) -> None:
        self._conn.execute(
            "INSERT INTO trades (trade_id, run_id, symbol, entry_fill_id, exit_fill_id, shares, "
            "opened_at, closed_at, exit_reason, planned_risk, result_currency, result_r, "
            "risk_overrun, classification, opening_decision_id, closing_decision_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                trade_id,
                run_id,
                trade.symbol,
                entry_fill_id,
                exit_fill_id,
                trade.shares,
                _iso(trade.entry_fill.at),
                _iso(trade.exit_fill.at),
                trade.exit_reason.value,
                str(trade.planned_risk),
                str(trade.result_currency),
                str(trade.result_r),
                str(trade.risk_overrun),
                trade.classification.value if trade.classification else None,
                trade.opening_decision_id,
                trade.closing_decision_id,
            ),
        )
        self._conn.commit()

    def record_violation(self, run_id: str, at: datetime, rejection: Rejection) -> None:
        """Every refusal, not only the ones that surface.

        An empty violations table across a long run means the guards were never
        exercised — worth knowing, and the reason the risk tests provoke each kind.
        """
        self._conn.execute(
            "INSERT INTO violations (run_id, at, kind, statement, detail_json) VALUES (?,?,?,?,?)",
            (run_id, _iso(at), rejection.kind, rejection.statement, _json(rejection.evidence)),
        )
        self._conn.commit()

    def record_halt(self, run_id: str, at: datetime, kind: str, statement: str) -> None:
        self._conn.execute(
            "INSERT INTO halts (run_id, at, kind, statement) VALUES (?,?,?,?)",
            (run_id, _iso(at), kind, statement),
        )
        self._conn.commit()

    def record_review_note(
        self,
        *,
        run_id: str,
        trade_id: str,
        principle: str,
        expectation: str,
        outcome: str,
        supports_principle: bool,
        commentary: str,
    ) -> None:
        self._conn.execute(
            "INSERT INTO review_notes (run_id, trade_id, principle, expectation, outcome, "
            "supports_principle, commentary) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                trade_id,
                principle,
                expectation,
                outcome,
                1 if supports_principle else 0,
                commentary,
            ),
        )
        self._conn.commit()

    # -- readers ----------------------------------------------------------

    def decisions_on(self, day: date) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM decisions WHERE substr(as_of, 1, 10) = ? ORDER BY as_of",
                (day.isoformat(),),
            )
        )

    def decision(self, decision_id: str) -> sqlite3.Row | None:
        cursor = self._conn.execute(
            "SELECT * FROM decisions WHERE decision_id = ?", (decision_id,)
        )
        return cursor.fetchone()

    def verdicts_for(self, decision_id: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM verdicts WHERE decision_id = ? ORDER BY ordinal", (decision_id,)
            )
        )

    def decisions_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM decisions WHERE run_id = ? ORDER BY as_of", (run_id,)
            )
        )

    def trades_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT * FROM trades WHERE run_id = ? ORDER BY opened_at", (run_id,)
            )
        )

    def violations_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute("SELECT * FROM violations WHERE run_id = ? ORDER BY at", (run_id,))
        )

    def halts_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute("SELECT * FROM halts WHERE run_id = ? ORDER BY at", (run_id,))
        )

    def principle_counts(self, run_id: str) -> list[sqlite3.Row]:
        return list(
            self._conn.execute(
                "SELECT v.principle, COUNT(*) AS encounters, "
                "SUM(v.passed) AS passes FROM verdicts v "
                "JOIN decisions d ON d.decision_id = v.decision_id "
                "WHERE d.run_id = ? GROUP BY v.principle ORDER BY v.principle",
                (run_id,),
            )
        )

    def run(self, run_id: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()

    def run_status(self, run_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM run_events WHERE run_id = ? ORDER BY event_id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        return row["status"] if row else None

    def runs(self) -> list[sqlite3.Row]:
        return list(self._conn.execute("SELECT * FROM runs ORDER BY started_at DESC"))

    def iter_tables(self) -> Iterator[str]:
        for row in self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            yield row["name"]

    @property
    def connection(self) -> sqlite3.Connection:
        """Exposed for the append-only guard test, which must attempt an UPDATE."""
        return self._conn
