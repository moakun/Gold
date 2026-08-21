# Contract: Durable Records

**Feature**: 001-explainable-gold-bot | **Date**: 2026-08-21

These are the artifacts that outlive a run: the snapshot manifest that makes a backtest
reproducible, and the audit records that make every claim traceable. They are contracts because
other things read them — the journal renderer, the review-note generator, and the operator with a
question about a trade from six months ago.

## Snapshot manifest

`data/snapshots/<symbol>-<cadence>-<from>-<to>.manifest.json`, tracked in git while the bulk data
it describes is not.

```json
{
  "snapshot_id": "GLD-daily-2010-01-01-2026-08-20",
  "symbol": "GLD",
  "cadence": "daily",
  "source": "stooq",
  "fetched_at": "2026-08-21T14:02:11Z",
  "range": { "from": "2010-01-04", "to": "2026-08-20" },
  "row_count": 4187,
  "sha256": "9f2c…",
  "data_path": "data/raw/GLD-daily-2010-01-01-2026-08-20.csv",
  "notes": "Adjusted for splits; no dividend adjustment (fund pays none)."
}
```

**Contract**

- `sha256` is over the raw file bytes as fetched, before any parsing.
- The loader verifies the digest before every run and refuses on mismatch (CLI exit 3).
- A manifest is never rewritten in place. Re-fetching the same range from a changed upstream
  produces a **new** `snapshot_id`, so an old backtest stays reproducible.
- `row_count` is a cheap second check that catches truncated downloads a digest would also catch
  but less legibly.

## Audit database

One SQLite file. Every record table carries append-only triggers:

```sql
CREATE TRIGGER <table>_no_update BEFORE UPDATE ON <table>
BEGIN SELECT RAISE(ABORT, '<table> is append-only'); END;

CREATE TRIGGER <table>_no_delete BEFORE DELETE ON <table>
BEGIN SELECT RAISE(ABORT, '<table> is append-only'); END;
```

Applied to: `runs`, `decisions`, `verdicts`, `orders`, `fills`, `trades`, `violations`, `halts`,
`review_notes`.

### `runs`

| Column | Type | Notes |
|---|---|---|
| `run_id` | TEXT PK | |
| `mode` | TEXT | `BACKTEST` / `WALK_FORWARD` / `PAPER` |
| `snapshot_digest` | TEXT | `NULL` only for paper mode |
| `config_version` | TEXT | Content hash of the strategy config |
| `envelope_version` | TEXT | Content hash of the risk envelope |
| `code_version` | TEXT | Git commit, or `<commit>-dirty` |
| `started_at` / `finished_at` | TEXT | UTC ISO-8601 |
| `status` | TEXT | `RUNNING` / `COMPLETE` / `ABORTED` / `HALTED` |

`snapshot_digest`, `config_version`, and `code_version` together are the reproducibility triple
(SC-004).

### `decisions`

| Column | Type | Notes |
|---|---|---|
| `decision_id` | TEXT PK | Deterministic: hash of `run_id` + bar end |
| `run_id` | TEXT FK | |
| `as_of` | TEXT | UTC, the decision bar's end |
| `symbol` | TEXT | |
| `action` | TEXT | `ENTER` / `EXIT` / `HOLD` / `SKIP` |
| `explanation` | TEXT | Rendered, non-empty — enforced by a `CHECK` constraint as well as by the type |
| `blocking_rule_id` | TEXT | Non-null when `action = 'SKIP'` |
| `plan_json` | TEXT | Non-null when `action = 'ENTER'` |

**Contract**: exactly one row per completed bar evaluated, including `HOLD` and `SKIP` (FR-001).
A run whose decision count does not equal its evaluated-bar count is a defect, and an integration
test asserts the equality.

### `verdicts`

| Column | Type | Notes |
|---|---|---|
| `verdict_id` | INTEGER PK | |
| `decision_id` | TEXT FK | |
| `rule_id` | TEXT | |
| `principle` | TEXT | Must match a lesson id |
| `passed` | INTEGER | 0/1 |
| `evidence_json` | TEXT | The actual values compared |
| `statement` | TEXT | Non-empty |
| `ordinal` | INTEGER | Evaluation order, so the journal reads the way the logic ran |

**Contract**: every decision has ≥ 1 verdict. Rules do not short-circuit, so a `SKIP` carries the
verdicts that passed as well as the one that failed (FR-004, research.md R2).

### `orders` / `fills`

| `orders` column | Type | Notes |
|---|---|---|
| `order_id` | TEXT PK | |
| `decision_id` | TEXT FK | Never null — no order exists without its reasoning |
| `envelope_version` | TEXT | Which limits were in force |
| `side` | TEXT | `BUY` / `SELL` |
| `shares` | INTEGER | |
| `simulated` | INTEGER | `CHECK (simulated = 1)` — the database itself refuses a live order |

| `fills` column | Type | Notes |
|---|---|---|
| `fill_id` | TEXT PK | |
| `order_id` | TEXT FK | |
| `price` | TEXT | Decimal as string — never a float, to preserve exactness |
| `shares` | INTEGER | May be less than ordered |
| `commission` / `spread_cost` / `slippage_cost` | TEXT | Itemised, never a single opaque "cost" |
| `slippage_vs_intended` | TEXT | Required by FR-038 |

The `CHECK (simulated = 1)` constraint is worth noting: even if every other guard were bypassed,
the audit store would reject the write. FR-024 is enforced in four independent places — no SDK in
the lockfile, one `Broker` implementation, no network I/O in `execution/`, and this constraint.

Prices are stored as TEXT rather than REAL because SQLite's REAL is a float, and a round trip
through it would break the exact-decimal guarantee that reproducibility depends on.

### `violations`

| Column | Type | Notes |
|---|---|---|
| `violation_id` | INTEGER PK | |
| `run_id` | TEXT FK | |
| `at` | TEXT | UTC |
| `kind` | TEXT | `ALLOW_LIST` / `NO_STOP` / `RISK_EXCEEDED` / `WIDEN_STOP` / `AVERAGE_DOWN` / `MISSING_EXPLANATION` / `LOOK_AHEAD` |
| `detail_json` | TEXT | |

**Contract**: a violation row is written for every rejected attempt, not only for those that
surface to the operator. An empty `violations` table across a long run is evidence the guards were
never exercised — which is itself worth knowing, and the reason the risk-layer tests deliberately
provoke each kind.

### `trades`

Adds two columns beyond the obvious round-trip fields:

| Column | Type | Notes |
|---|---|---|
| `planned_risk` | TEXT | What was intended at entry |
| `risk_overrun` | TEXT | Positive when a gap produced a worse fill than the stop |
| `classification` | TEXT | `CORRECT` / `RULE_VIOLATION` / `SYSTEM_ERROR` (FR-031) |
| `exit_reason` | TEXT | `STOP` / `TARGET` / `RULE` / `GAP_THROUGH_STOP` / `KILL_SWITCH` |

`risk_overrun` exists so that the honest question — *did the 1% rule actually hold?* — can be
answered from the data instead of assumed. For an instrument closed most of the day, it will
sometimes be non-zero, and the report surfaces the count.

## Exported decision record

`goldbot journal show --decision ID --json` emits the shape other tooling should depend on:

```json
{
  "decision_id": "…",
  "as_of": "2026-08-20T20:00:00Z",
  "symbol": "GLD",
  "action": "SKIP",
  "explanation": "No entry: trend and momentum aligned, but the setup was vetoed …",
  "verdicts": [
    {
      "rule_id": "trend_filter",
      "principle": "trend-alignment",
      "passed": true,
      "evidence": { "close": "312.44", "sma_200": "298.10" },
      "statement": "Close 312.44 is above its 200-day average 298.10"
    },
    {
      "rule_id": "event_blackout",
      "principle": "event-risk",
      "passed": false,
      "evidence": { "event": "FOMC", "hours_until": "18" },
      "statement": "An FOMC decision lands in 18 hours; policy sets the standing rule to stand aside"
    }
  ],
  "blocking_rule_id": "event_blackout",
  "plan": null
}
```

**Contract**: `verdicts` is ordered by evaluation order and includes passing verdicts. Decimal
values are strings. A consumer reading only `explanation` gets the prose; a consumer reading
`verdicts` gets the machine-checkable reasoning behind it, and the two can never disagree because
the prose is rendered from the verdicts.
