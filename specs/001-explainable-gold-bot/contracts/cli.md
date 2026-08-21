# Contract: Command-Line Surface

**Feature**: 001-explainable-gold-bot | **Date**: 2026-08-21

The CLI is the only interface this feature exposes. Everything below is a contract: argument
names, exit codes, and the guarantees each command makes are stable, and changing them is a
breaking change.

Invoked as `goldbot <group> <command>`. All commands accept `--json` for machine-readable output
and `--quiet` to suppress the Rich rendering.

## Global guarantees

- **No command reaches a live brokerage account.** No such code path exists (FR-024).
- **No command mutates an existing audit record.** The store rejects updates at the database
  level (FR-025).
- **Every command that produces a trading decision writes it to the audit store before acting on
  it**, never after.
- Commands are safe to interrupt. A half-finished run leaves a `RunArtifact` marked `ABORTED`
  rather than a corrupt journal.

## `goldbot data`

### `data pull`

```
goldbot data pull --symbol SYMBOL --from YYYY-MM-DD --to YYYY-MM-DD
                  [--source stooq|tiingo|alpaca] [--cadence daily|4h]
```

Fetches bars, writes bulk data to `data/raw/`, computes SHA-256, and writes a manifest to
`data/snapshots/<symbol>-<cadence>-<from>-<to>.manifest.json`.

**Guarantees**: never overwrites an existing snapshot with a different digest — a changed
upstream produces a new snapshot id and a warning, not a silent replacement. `--source alpaca` is
rejected unless `--cadence 4h`, and requires `ALPACA_API_KEY` / `ALPACA_API_SECRET` in the
environment (the only credentials this version can use; the default daily path needs none).

### `data verify`

```
goldbot data verify [--snapshot SNAPSHOT_ID]
```

Recomputes digests and compares against manifests. Exit code 3 on any mismatch.

## `goldbot backtest`

```
goldbot backtest --snapshot SNAPSHOT_ID --config CONFIG_PATH [--out RUN_DIR]
```

Runs the strategy over a pinned snapshot. Refuses to start if the snapshot digest does not match
its manifest (exit 3).

**Outputs**: a `RunArtifact` in the audit store, a Markdown decision journal, and a performance
report.

**Guarantees**:

- One decision record per completed bar, including no-trade bars (FR-001).
- Identical output for identical snapshot, config, and code version (SC-004).
- The report presents the full metric set; there is no flag that prints a single metric
  (FR-026).
- Any rule that attempts to read beyond the decision bar aborts the run with `LookAheadError`
  (exit 4), rather than producing results.

## `goldbot walkforward`

```
goldbot walkforward --snapshot SNAPSHOT_ID --config CONFIG_PATH
                    --train-until YYYY-MM-DD [--folds N]
```

Same engine, evaluated on data held out from parameter selection. Records the result against the
strategy's `PromotionState`.

## `goldbot paper`

```
goldbot paper run --config CONFIG_PATH [--cadence daily|4h]
goldbot paper status
```

Runs the same decision loop forward in real time with a live data feed and simulated fills.

**Guarantees**:

- Fills are simulated in-process; no order is transmitted anywhere (FR-024).
- Decisions on a completed daily bar execute at the next session's open, and the journal records
  the difference between the trigger price and the price obtained (FR-038).
- On stale data, fetch failure, or an unhandled error in the decision path, the session enters
  SAFE mode: no new entries, existing stop preserved, operator alerted, exit 5 (FR-017).
- Reaching the daily loss limit blocks new entries and requires `goldbot paper resume` — it does
  not clear itself at midnight (FR-014).

## `goldbot kill`

```
goldbot kill [--clear]
```

Cancels working orders, flattens simulated positions, writes a halt record, and sets a latch that
blocks all new entries. `--clear` releases the latch and is the only way to release it.

**Guarantee**: completes within 10 seconds (SC-008). Safe to run when nothing is open — it is
idempotent.

## `goldbot journal`

```
goldbot journal show [--run RUN_ID] [--date YYYY-MM-DD] [--decision DECISION_ID]
goldbot journal why  --date YYYY-MM-DD
```

`why` is the SC-007 path: given a date, print the full reasoning for what the system did — or
explain why it did nothing — in one command.

## `goldbot report`

```
goldbot report --run RUN_ID
```

Prints expectancy, win rate, average R multiple, maximum drawdown, trade count, return net of
costs, the count of trades whose realised loss exceeded planned risk, and the fund's disclosed
expense ratio. All of them, always (FR-026).

## `goldbot lessons`

```
goldbot lessons list
goldbot lessons show PRINCIPLE_ID
goldbot lessons coverage [--run RUN_ID]
goldbot lessons review --trade TRADE_ID
```

`coverage` reports which principles have appeared in real decisions and how often (FR-032).
`review` shows the closed-trade review note contrasting expectation with outcome (FR-030).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Unexpected error |
| 2 | Usage error — bad arguments |
| 3 | Data integrity failure — digest mismatch, gapped bars, invalid OHLC |
| 4 | Guard triggered — look-ahead detected, allow-list rejection, risk-envelope breach, missing explanation |
| 5 | Halted — SAFE mode, daily loss limit, or kill-switch latch set |

Codes 3, 4, and 5 are distinct on purpose. They mean, respectively: *the data is wrong*, *the code
tried something forbidden*, and *the system stopped itself deliberately*. Collapsing them would
make the most important failure — a guard firing — indistinguishable from a bad download.
