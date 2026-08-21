# Phase 1 Data Model: Explainable Gold Trading Bot

**Feature**: 001-explainable-gold-bot | **Date**: 2026-08-21

Types are frozen dataclasses unless stated otherwise. All monetary and price values are `Decimal`
under a single pinned context (research.md R7). All timestamps are timezone-aware UTC.

Validation described as "constructor" is enforced in `__post_init__` and raises — these are the
invariants that turn requirements into structural impossibilities rather than review comments.

## Dependency direction

```
domain/  ←  strategy/     (reads bars, returns verdicts)
   ↑     ←  risk/         (reads decisions + account, mints authorizations)
   ↑     ←  execution/    (consumes authorizations, produces fills)
   └─────←  engine/       (composes all of the above)
```

`domain/` imports nothing from the other layers. This is asserted by a test in
`tests/constitution/`.

## Core types

### Bar

One completed period of price history.

| Field | Type | Notes |
|---|---|---|
| `symbol` | `str` | Must be on the allow-list |
| `start` / `end` | `datetime` | UTC, timezone-aware |
| `open` / `high` / `low` / `close` | `Decimal` | Positive |
| `volume` | `int` | Non-negative |
| `is_complete` | `bool` | Partial 4-hour remainder bars are `False` |

**Constructor validation**: `low <= open, close <= high`; `low <= high`; all prices positive;
`start < end`; timestamps must be UTC-aware. A bar failing these is a data defect, not a trading
signal — it raises rather than being silently dropped, per the missing-data edge case.

**Rule**: only `is_complete=True` bars may trigger a decision (FR-034, Principle IV).

### MarketView

A bounded window over the bar sequence, ending at the decision bar.

| Field | Type | Notes |
|---|---|---|
| `bars` | `tuple[Bar, ...]` | Everything up to and including the decision bar |
| `as_of` | `datetime` | The decision bar's `end` |

**The point of this type**: indexing beyond `as_of` raises `LookAheadError`. There is no accessor
that returns a future bar. This makes FR-022 a runtime guarantee rather than a review discipline —
a peeking rule fails a unit test instead of producing an excellent, untradeable backtest
(research.md R8).

### Verdict

The atom of explanation. Every rule returns exactly one.

| Field | Type | Notes |
|---|---|---|
| `rule_id` | `str` | Stable identifier |
| `principle` | `str` | Must resolve to a lesson file (SC-010) |
| `passed` | `bool` | |
| `evidence` | `Mapping[str, Decimal \| str]` | The actual values used, e.g. `{"close": 312.44, "sma_200": 298.10}` |
| `statement` | `str` | One human line: "Close 312.44 is above its 200-day average 298.10" |

**Constructor validation**: `statement` non-empty; `evidence` non-empty; `principle` non-empty.
An unexplainable rule cannot produce a valid `Verdict`, and therefore cannot reach the order path
(FR-007).

*Maps to the spec's "Signal" entity.* Renamed because the design carries the judgment and its
justification together rather than as separate objects.

### Decision

The central artifact. One per market evaluation, including no-trade evaluations (FR-001).

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | Deterministic: hash of run id + bar end |
| `as_of` | `datetime` | Decision bar's end, UTC |
| `symbol` | `str` | |
| `action` | `Action` | `ENTER` / `EXIT` / `HOLD` / `SKIP` |
| `verdicts` | `tuple[Verdict, ...]` | All rules evaluated, passed and failed alike |
| `explanation` | `str` | Rendered from verdicts |
| `plan` | `EntryPlan \| None` | Required when `action == ENTER` |
| `blocking_verdict` | `Verdict \| None` | Required when `action == SKIP` — the condition that vetoed |

**Constructor validation**:

- `verdicts` non-empty — a decision without reasoning cannot exist (FR-006).
- `action == ENTER` requires `plan`; `action == SKIP` requires `blocking_verdict` (FR-004).
- `explanation` non-empty.

**No short-circuiting**: `verdicts` holds every rule evaluated, not just the decisive one.
Explaining a skip requires knowing which conditions *passed* too (research.md R2).

### EntryPlan

Everything FR-003 requires an entry decision to state.

| Field | Type | Notes |
|---|---|---|
| `intended_entry` | `Decimal` | Next session's open is unknown at decision time; this is the trigger price |
| `stop` | `Decimal` | The invalidation level |
| `target` | `Decimal \| None` | |
| `shares` | `int` | Whole shares, ≥ 1 |
| `risk_amount` | `Decimal` | `shares × (intended_entry − stop)` |
| `risk_pct` | `Decimal` | Of account equity; must be ≤ the envelope limit |
| `reward_risk` | `Decimal \| None` | Present when `target` is set |
| `binding_constraint` | `Constraint` | `RISK_BUDGET` / `AVAILABLE_CASH` / `NONE` — which limit set the size (research.md R11) |

**Constructor validation**: `stop < intended_entry` (long-only, FR-037); `shares >= 1`;
`risk_pct <= envelope.max_risk_per_trade` (FR-013).

### Authorization

A capability token. The only thing `SimulatedBroker` accepts.

| Field | Type | Notes |
|---|---|---|
| `decision_id` | `str` | Links back to the reasoning |
| `plan` | `EntryPlan` | |
| `issued_at` | `datetime` | |
| `envelope_version` | `str` | Which risk envelope was in force |

**Minted only by `RiskGate.authorize`.** There is no public constructor. This is the mechanism
behind Principle I: no code path creates an order without passing the risk checks, because the
broker will not accept anything else (FR-012).

### Order / Fill

| Order field | Type | Notes |
|---|---|---|
| `id` | `str` | |
| `authorization` | `Authorization` | Required — no unauthorized order type exists |
| `side` | `Side` | `BUY` / `SELL` only; no short side is representable (FR-037) |
| `shares` | `int` | |
| `submitted_at` | `datetime` | |
| `simulated` | `Literal[True]` | Always true in this version (FR-024) |

| Fill field | Type | Notes |
|---|---|---|
| `order_id` | `str` | |
| `price` | `Decimal` | Actual simulated execution price |
| `shares` | `int` | May be less than ordered — partial fills recalculate risk |
| `costs` | `Costs` | Commission, spread, slippage, itemised |
| `slippage_vs_intended` | `Decimal` | Required by FR-038 |

### Position

| Field | Type | Notes |
|---|---|---|
| `symbol` | `str` | |
| `shares` | `int` | Positive — long only |
| `entry_price` | `Decimal` | |
| `stop` | `Decimal` | |
| `opened_at` | `datetime` | |
| `opening_decision_id` | `str` | |

**Frozen, with no mutating operations.** There is deliberately no `widen_stop`, no `remove_stop`,
and no `add_shares`. The forbidden operations of Principle I are not blocked at runtime — they are
absent from the type, so calling them is a `AttributeError` at development time rather than a
policy violation at trading time (FR-015).

Tightening a stop is permitted and is modelled as replacing the position with a new frozen
instance; a test asserts the replacement's stop is strictly closer to price than its predecessor's.

### Trade

A completed round trip.

| Field | Type | Notes |
|---|---|---|
| `entry_fill` / `exit_fill` | `Fill` | |
| `result_currency` | `Decimal` | Net of all costs |
| `result_r` | `Decimal` | Multiples of initial risk |
| `exit_reason` | `ExitReason` | `STOP` / `TARGET` / `RULE` / `GAP_THROUGH_STOP` / `KILL_SWITCH` |
| `planned_risk` | `Decimal` | |
| `risk_overrun` | `Decimal` | Positive when a gap produced a worse fill than the stop |
| `classification` | `LossClass \| None` | `CORRECT` / `RULE_VIOLATION` / `SYSTEM_ERROR` (FR-031) |

`risk_overrun` exists because stops are intentions, not guarantees — the overnight gap case is
structural for this instrument, and expectancy must be judged including it.

## Configuration and control

### RiskEnvelope

| Field | Type | Default |
|---|---|---|
| `max_risk_per_trade` | `Decimal` | `0.010` |
| `max_daily_loss` | `Decimal` | `0.030` |
| `max_concurrent_positions` | `int` | `1` |
| `max_leverage` | `Decimal` | `2.0` (never binding in a cash account) |
| `version` | `str` | Content hash |

**Immutable during a run** (FR-018). The engine snapshots it at start; a changed envelope requires
a restart, and the version is recorded on every authorization.

### Instrument

| Field | Type | Notes |
|---|---|---|
| `symbol` | `str` | |
| `calendar` | `str` | e.g. `XNYS` |
| `expense_ratio` | `Decimal` | Disclosed in reports; **not** applied as a cost (research.md R10) |
| `commission_per_share` / `commission_min` | `Decimal` | |

The allow-list is a tuple of `Instrument`. Anything not in it is rejected inside
`RiskGate.authorize`, before an `Authorization` can exist (FR-009, FR-010).

### PromotionState

State machine per strategy version (FR-023):

```
BACKTEST ──(criteria met)──> WALK_FORWARD ──(criteria met)──> PAPER ──✗ blocked in v1
```

Each transition records the run artifact that justified it. `PAPER → LIVE` is unreachable: the
`LIVE` state is not defined in this version (FR-024, FR-035).

## Run and reporting

### RunArtifact

| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | |
| `mode` | `Mode` | `BACKTEST` / `WALK_FORWARD` / `PAPER` |
| `snapshot_digest` | `str` | SHA-256 of the pinned data |
| `config_version` | `str` | |
| `envelope_version` | `str` | |
| `started_at` / `finished_at` | `datetime` | |
| `code_version` | `str` | Git commit, or `dirty` |

`snapshot_digest + config_version + code_version` is the reproducibility triple. SC-004 asserts
that two runs sharing all three produce identical decision journals.

### PerformanceReport

Computed, not stored. Deliberately exposes **no single-metric accessor** — the only public method
returns the full set, so FR-026 cannot be violated by a caller reaching for the flattering number.

Includes: expectancy, win rate, average R, maximum drawdown, trade count, total return net of
costs, count of trades whose realised loss exceeded planned risk, and the disclosed expense ratio.

## Learning layer

### Lesson

Markdown files under `src/goldbot/lessons/content/`, one per principle id, with front matter for
the id and title, and sections for what the concept is, when it works, when it fails, and how it
behaves in gold.

**Integrity rule**: a test enumerates every `principle` emitted by any rule and asserts a matching
lesson exists. Adding a rule without its lesson fails the suite (SC-010, constitution workflow).

### ReviewNote

| Field | Type | Notes |
|---|---|---|
| `trade` | `Trade` | |
| `expectation` | `str` | Lifted from the entry decision's explanation |
| `outcome` | `str` | |
| `supports_principle` | `bool` | |
| `commentary` | `str` | |

### PrincipleCoverage

Aggregate view: principle id, times encountered, times it led to a trade, and the win rate when it
did (FR-032). This is what turns scattered explanations into a picture of what the operator has
actually seen the market do.

## Audit store

SQLite, one file per environment. Tables mirror the types above: `runs`, `decisions`, `verdicts`,
`orders`, `fills`, `trades`, `violations`, `halts`, `review_notes`.

**Append-only is enforced by the database**, not by convention:

```sql
CREATE TRIGGER decisions_no_update BEFORE UPDATE ON decisions
BEGIN SELECT RAISE(ABORT, 'decisions is append-only'); END;
```

Equivalent triggers cover every record table for both `UPDATE` and `DELETE` (FR-025, Principle V).

## Entity mapping to the specification

| Spec entity | Design type | Note |
|---|---|---|
| Instrument | `Instrument` | |
| Market Bar | `Bar` | Plus `MarketView` for bounded access |
| Signal | `Verdict` | Renamed: judgment and justification travel together |
| Decision Record | `Decision` | |
| Order | `Order` + `Authorization` | Split so authorization is a capability, not a boolean |
| Fill | `Fill` | |
| Position | `Position` | Frozen; forbidden operations absent by construction |
| Trade | `Trade` | Adds `risk_overrun` for the gap case |
| Risk Envelope | `RiskEnvelope` | |
| Run Artifact | `RunArtifact` | |
| Performance Report | `PerformanceReport` | |
| Lesson | `Lesson` | Markdown content, not a database row |
| Review Note | `ReviewNote` | |
| Promotion State | `PromotionState` | `LIVE` deliberately undefined |
