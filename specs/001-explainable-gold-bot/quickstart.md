# Quickstart & Validation Guide

**Feature**: 001-explainable-gold-bot | **Date**: 2026-08-21

How to run the system once it exists, and the scenarios that prove it does what
[spec.md](./spec.md) requires. Each scenario names the requirement it validates, so a failing
scenario points at a specific obligation rather than a vague regression.

## Prerequisites

- Python 3.11 or newer (3.11.8 is what this was developed against)
- [uv](https://docs.astral.sh/uv/) 0.11 or newer
- Network access for the initial data pull only — every later step runs offline
- **No API credentials.** The default daily path is unauthenticated by design (research.md R4).
  Credentials are needed only for the optional 4-hour cadence.

## Setup

```bash
uv sync
```

Installs from the committed lockfile. The lockfile is tracked precisely because pinned
dependencies are part of what makes a run reproducible (Principle V).

```bash
uv run goldbot --version
```

Expected: version string and a line confirming `execution: simulated only`.

## Scenario 1 — Pin a data snapshot

**Validates**: FR-020 (reproducible from pinned data), Principle V

```bash
uv run goldbot data pull --symbol GLD --from 2010-01-01 --to 2026-08-20
```

Expected:

- A CSV under `data/raw/` (gitignored) and a manifest under `data/snapshots/` (tracked)
- The manifest reports source, row count, and a SHA-256 digest
- Console warns if the range contains fewer bars than trading days in the period

```bash
uv run goldbot data verify
```

Expected: every snapshot verifies, exit code 0. Corrupt a byte of the CSV and re-run: exit code 3
with the mismatched digest named. **This failure is the feature** — it is what stops a silently
altered dataset from producing a plausible backtest.

## Scenario 2 — An explained backtest

**Validates**: User Story 1, FR-001 to FR-005, FR-021, FR-026

```bash
uv run goldbot backtest --snapshot GLD-daily-2010-01-01-2026-08-20 --config config/baseline.toml
```

Expected:

- A run id, a Markdown journal, and a performance report
- **One decision record per completed bar**, including the many days the system did nothing.
  Reported as `decisions: N (enter: a, exit: b, hold: c, skip: d)` where `N` equals the bar count
- The report shows expectancy, win rate, average R, max drawdown, trade count, net return, the
  count of trades whose realised loss exceeded planned risk, and the fund's expense ratio — all of
  them, with no flag that prints one alone
- Results are net of spread, commission, and slippage. A report showing zero total cost is a bug

Read a single skipped day:

```bash
uv run goldbot journal why --date 2026-03-14
```

Expected: the conditions that passed, the one that failed, and the named principle behind it — not
just "no signal".

## Scenario 3 — Reproducibility

**Validates**: SC-004, FR-020

```bash
uv run goldbot backtest --snapshot GLD-daily-2010-01-01-2026-08-20 --config config/baseline.toml --out runs/a
uv run goldbot backtest --snapshot GLD-daily-2010-01-01-2026-08-20 --config config/baseline.toml --out runs/b
```

```bash
diff runs/a/journal.md runs/b/journal.md
```

Expected: no output. Identical snapshot, config, and code version produce byte-identical journals.
Any difference means non-determinism has crept into the decision path — almost always a wall-clock
read, a float accumulation, or an unordered iteration.

## Scenario 4 — The guards actually fire

**Validates**: FR-006, FR-010, FR-012, FR-013, FR-015, FR-022 — Principles I, II, III

These are the tests that matter most, because a risk control never exercised is a risk control
never proven.

```bash
uv run pytest tests/constitution -v
```

Expected, all passing:

| Test | Asserts |
|---|---|
| `test_no_live_broker` | No brokerage SDK in the lockfile; `Broker` has exactly one implementation |
| `test_no_lookahead` | A rule reaching past the decision bar raises `LookAheadError` |
| `test_authorization_unforgeable` | `Authorization` cannot be constructed outside `RiskGate` |
| `test_no_orphan_principles` | Every principle emitted by a rule has a lesson file |
| `test_no_wallclock` | No wall-clock read reachable from `strategy/`, `risk/`, or `engine/` |
| `test_rules_are_pure` | No I/O or randomness reachable from `strategy/` |
| `test_append_only` | `UPDATE` and `DELETE` on any record table raise |

Then provoke the risk layer directly:

```bash
uv run goldbot backtest --snapshot GLD-daily-2010-01-01-2026-08-20 --config config/violations-probe.toml
```

A config that requests a non-gold symbol, a stop-less entry, and an oversized position. Expected:
exit code 4, and a `violations` table containing one row per rejected attempt with a human-readable
statement for each.

## Scenario 5 — Paper trading with enforced limits

**Validates**: User Story 2, FR-014, FR-016, FR-017, FR-024, FR-038

```bash
uv run goldbot paper run --config config/baseline.toml
```

Expected across a session:

- Each decision prints as it is made, with its reasoning
- A decision made on a completed daily bar executes at the **next session's open**, and the
  journal records the difference between the trigger price and the price obtained
- No network call transmits an order — verify with `goldbot paper status`, which reports
  `execution: simulated`

Force the halt:

```bash
uv run goldbot paper run --config config/forced-loss.toml
```

Expected: on reaching the 3% daily loss, new entries stop, a `halts` row is written with the
reason, exit code 5, and the session refuses to resume without `goldbot paper resume`. It does not
clear itself overnight.

Test the kill switch while a position is open:

```bash
uv run goldbot kill
```

Expected: positions flattened, working orders cancelled, halt recorded, latch set, all within 10
seconds (SC-008). New entries stay blocked until `goldbot kill --clear`.

## Scenario 6 — The learning layer

**Validates**: User Story 3, FR-029 to FR-032, SC-010

```bash
uv run goldbot lessons coverage --run <RUN_ID>
```

Expected: every principle the strategy used, how often it appeared, how often it led to a trade,
and the win rate when it did. A principle with zero encounters is fine and informative — it means
the market has not shown you that situation yet.

```bash
uv run goldbot lessons show trend-alignment
uv run goldbot lessons review --trade <TRADE_ID>
```

Expected: the lesson covers what the concept is, when it works, when it fails, and how it behaves
in gold. The review note contrasts what was expected at entry with what happened, and states
whether the outcome supports or contradicts the principle.

Check the honesty of the loss classification:

```bash
uv run goldbot report --run <RUN_ID>
```

Expected: losing trades are split into correctly-taken losses and losses from rule violations or
errors. In a clean backtest the second category should be empty — if it is not, that is the most
important number in the report.

## Scenario 7 — Gap reality check

**Validates**: the structural caveat in the spec — stops are intentions, not guarantees

```bash
uv run goldbot report --run <RUN_ID>
```

Look at `trades where risk_overrun > 0`. Expected: a non-zero count over any multi-year backtest.
This instrument is closed roughly seventeen and a half hours a weekday plus weekends, so some
positions reopen beyond their stop.

A backtest reporting zero overruns across years of daily bars is not good news — it means the fill
model is assuming stops always execute at their price, which would flatter every result in the
report.

## What "done" looks like

| Requirement group | Proven by |
|---|---|
| Every decision explained (FR-001–008) | Scenarios 2, 4 |
| Gold-only (FR-009–011) | Scenario 4 |
| Risk enforcement (FR-012–019) | Scenarios 4, 5 |
| Simulation discipline (FR-020–024) | Scenarios 1, 3, 4, 5 |
| Audit & reporting (FR-025–028) | Scenarios 2, 4, 6 |
| Learning layer (FR-029–032) | Scenario 6 |
| Instrument & cadence (FR-033–038) | Scenarios 1, 5, 7 |
