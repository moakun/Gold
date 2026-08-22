-- The audit store.
--
-- Append-only is enforced here, by the database, rather than by the method
-- surface above it. A convention developers remember is not the same thing as
-- a table that refuses UPDATE.
--
-- Decimals are stored as TEXT. SQLite's REAL is a float, and a round trip
-- through one would break the exact-decimal guarantee that reproducibility
-- depends on.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- Immutable identity of a run. The reproducibility triple lives here:
-- snapshot_digest + config_version + code_version.
CREATE TABLE IF NOT EXISTS runs (
    run_id           TEXT PRIMARY KEY,
    mode             TEXT NOT NULL CHECK (mode IN ('BACKTEST', 'WALK_FORWARD', 'PAPER')),
    symbol           TEXT NOT NULL,
    snapshot_digest  TEXT,
    config_version   TEXT NOT NULL,
    envelope_version TEXT NOT NULL,
    code_version     TEXT NOT NULL,
    started_at       TEXT NOT NULL
);

-- Status is a sequence of appended events rather than a mutable column.
-- Marking a run complete by UPDATE would have required exempting `runs` from
-- the append-only rule, and an audit log with one exemption is an audit log
-- with one exemption. Current status is the latest event.
CREATE TABLE IF NOT EXISTS run_events (
    event_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    at             TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('RUNNING','COMPLETE','ABORTED','HALTED')),
    bars_evaluated INTEGER NOT NULL DEFAULT 0,
    note           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS run_events_by_run ON run_events(run_id, event_id);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id     TEXT PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    as_of           TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    action          TEXT NOT NULL CHECK (action IN ('ENTER','EXIT','HOLD','SKIP')),
    explanation     TEXT NOT NULL CHECK (length(trim(explanation)) > 0),
    blocking_rule_id TEXT,
    plan_json       TEXT,
    CHECK (action <> 'ENTER' OR plan_json IS NOT NULL),
    CHECK (action <> 'SKIP'  OR blocking_rule_id IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS decisions_by_date ON decisions(substr(as_of, 1, 10));
CREATE INDEX IF NOT EXISTS decisions_by_run ON decisions(run_id);

CREATE TABLE IF NOT EXISTS verdicts (
    verdict_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id   TEXT NOT NULL REFERENCES decisions(decision_id),
    ordinal       INTEGER NOT NULL,
    rule_id       TEXT NOT NULL,
    principle     TEXT NOT NULL,
    passed        INTEGER NOT NULL CHECK (passed IN (0, 1)),
    evidence_json TEXT NOT NULL,
    statement     TEXT NOT NULL CHECK (length(trim(statement)) > 0)
);

CREATE INDEX IF NOT EXISTS verdicts_by_decision ON verdicts(decision_id);
CREATE INDEX IF NOT EXISTS verdicts_by_principle ON verdicts(principle);

CREATE TABLE IF NOT EXISTS orders (
    order_id         TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL REFERENCES runs(run_id),
    decision_id      TEXT NOT NULL REFERENCES decisions(decision_id),
    envelope_version TEXT NOT NULL,
    side             TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    shares           INTEGER NOT NULL CHECK (shares > 0),
    submitted_at     TEXT NOT NULL,
    -- The fourth independent guard on FR-024. Even if every other check were
    -- bypassed, the audit store refuses to record a live order.
    simulated        INTEGER NOT NULL DEFAULT 1 CHECK (simulated = 1)
);

CREATE TABLE IF NOT EXISTS fills (
    fill_id              TEXT PRIMARY KEY,
    order_id             TEXT NOT NULL REFERENCES orders(order_id),
    decision_id          TEXT NOT NULL,
    symbol               TEXT NOT NULL,
    side                 TEXT NOT NULL,
    price                TEXT NOT NULL,
    shares               INTEGER NOT NULL CHECK (shares > 0),
    filled_at            TEXT NOT NULL,
    commission           TEXT NOT NULL,
    spread_cost          TEXT NOT NULL,
    slippage_cost        TEXT NOT NULL,
    slippage_vs_intended TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    trade_id            TEXT PRIMARY KEY,
    run_id              TEXT NOT NULL REFERENCES runs(run_id),
    symbol              TEXT NOT NULL,
    entry_fill_id       TEXT NOT NULL,
    exit_fill_id        TEXT NOT NULL,
    shares              INTEGER NOT NULL,
    opened_at           TEXT NOT NULL,
    closed_at           TEXT NOT NULL,
    exit_reason         TEXT NOT NULL,
    planned_risk        TEXT NOT NULL,
    result_currency     TEXT NOT NULL,
    result_r            TEXT NOT NULL,
    -- Non-zero when the market reopened beyond the stop. The number that keeps
    -- "the 1% rule held" a measurement rather than an assumption.
    risk_overrun        TEXT NOT NULL,
    classification      TEXT,
    opening_decision_id TEXT NOT NULL,
    closing_decision_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS violations (
    violation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL REFERENCES runs(run_id),
    at           TEXT NOT NULL,
    kind         TEXT NOT NULL,
    statement    TEXT NOT NULL,
    detail_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS halts (
    halt_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id    TEXT NOT NULL REFERENCES runs(run_id),
    at        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    statement TEXT NOT NULL,
    cleared   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS review_notes (
    note_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT NOT NULL REFERENCES runs(run_id),
    trade_id          TEXT NOT NULL,
    principle         TEXT NOT NULL,
    expectation       TEXT NOT NULL,
    outcome           TEXT NOT NULL,
    supports_principle INTEGER NOT NULL CHECK (supports_principle IN (0, 1)),
    commentary        TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Append-only, enforced by the database (FR-025, Principle V).
--
-- Every record table refuses UPDATE and DELETE. History is what makes a
-- performance claim checkable, and history you can edit is not history.
-- ---------------------------------------------------------------------------

CREATE TRIGGER IF NOT EXISTS runs_no_update BEFORE UPDATE ON runs
BEGIN SELECT RAISE(ABORT, 'runs is append-only'); END;

CREATE TRIGGER IF NOT EXISTS runs_no_delete BEFORE DELETE ON runs
BEGIN SELECT RAISE(ABORT, 'runs is append-only'); END;

CREATE TRIGGER IF NOT EXISTS run_events_no_update BEFORE UPDATE ON run_events
BEGIN SELECT RAISE(ABORT, 'run_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS run_events_no_delete BEFORE DELETE ON run_events
BEGIN SELECT RAISE(ABORT, 'run_events is append-only'); END;

CREATE TRIGGER IF NOT EXISTS decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions is append-only'); END;

CREATE TRIGGER IF NOT EXISTS decisions_no_delete BEFORE DELETE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions is append-only'); END;

CREATE TRIGGER IF NOT EXISTS verdicts_no_update BEFORE UPDATE ON verdicts
BEGIN SELECT RAISE(ABORT, 'verdicts is append-only'); END;

CREATE TRIGGER IF NOT EXISTS verdicts_no_delete BEFORE DELETE ON verdicts
BEGIN SELECT RAISE(ABORT, 'verdicts is append-only'); END;

CREATE TRIGGER IF NOT EXISTS orders_no_update BEFORE UPDATE ON orders
BEGIN SELECT RAISE(ABORT, 'orders is append-only'); END;

CREATE TRIGGER IF NOT EXISTS orders_no_delete BEFORE DELETE ON orders
BEGIN SELECT RAISE(ABORT, 'orders is append-only'); END;

CREATE TRIGGER IF NOT EXISTS fills_no_update BEFORE UPDATE ON fills
BEGIN SELECT RAISE(ABORT, 'fills is append-only'); END;

CREATE TRIGGER IF NOT EXISTS fills_no_delete BEFORE DELETE ON fills
BEGIN SELECT RAISE(ABORT, 'fills is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trades_no_update BEFORE UPDATE ON trades
BEGIN SELECT RAISE(ABORT, 'trades is append-only'); END;

CREATE TRIGGER IF NOT EXISTS trades_no_delete BEFORE DELETE ON trades
BEGIN SELECT RAISE(ABORT, 'trades is append-only'); END;

CREATE TRIGGER IF NOT EXISTS violations_no_update BEFORE UPDATE ON violations
BEGIN SELECT RAISE(ABORT, 'violations is append-only'); END;

CREATE TRIGGER IF NOT EXISTS violations_no_delete BEFORE DELETE ON violations
BEGIN SELECT RAISE(ABORT, 'violations is append-only'); END;

CREATE TRIGGER IF NOT EXISTS halts_no_update BEFORE UPDATE ON halts
BEGIN SELECT RAISE(ABORT, 'halts is append-only'); END;

CREATE TRIGGER IF NOT EXISTS halts_no_delete BEFORE DELETE ON halts
BEGIN SELECT RAISE(ABORT, 'halts is append-only'); END;

CREATE TRIGGER IF NOT EXISTS review_notes_no_update BEFORE UPDATE ON review_notes
BEGIN SELECT RAISE(ABORT, 'review_notes is append-only'); END;

CREATE TRIGGER IF NOT EXISTS review_notes_no_delete BEFORE DELETE ON review_notes
BEGIN SELECT RAISE(ABORT, 'review_notes is append-only'); END;
