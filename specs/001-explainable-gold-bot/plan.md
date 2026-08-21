# Implementation Plan: Explainable Gold Trading Bot

**Branch**: `001-explainable-gold-bot` | **Date**: 2026-08-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-explainable-gold-bot/spec.md`

## Summary

Build a long-or-flat gold ETF swing strategy whose reasoning is the primary artifact, not a
by-product. The core move is architectural: rules return `Verdict` objects carrying evidence,
principle, and a human statement; a `Decision` is constructed from its verdicts and cannot exist
without them; an `Order` can only be created from a `Decision` and only reaches the broker through
a `RiskGate`. Three requirements that would normally be code-review conventions — explain every
decision (FR-006), never trade without a stop (FR-012), never peek at future bars (FR-022) — become
structural impossibilities enforced by constructors and a bounded `MarketView`.

A small event-driven engine drives both the backtest and the paper session over the same code
path, differing only in which `DataFeed` and `Clock` are injected. Fills are simulated in-process
and no brokerage trading SDK is installed, so FR-024 ("no live path exists") is verifiable by
absence rather than asserted by a flag. See [research.md](./research.md) for the decisions and
what was rejected.

## Technical Context

**Language/Version**: Python 3.11+ (3.11.8 installed locally), managed by uv 0.11.31 with a
committed lockfile

**Primary Dependencies**: `httpx` (snapshot fetch), `exchange_calendars` (XNYS sessions, holidays,
half-days), `typer` (CLI), `rich` (on-screen decision output), `pandas` (I/O boundary only — the
engine operates on frozen `Bar` dataclasses). Dev: `pytest`, `pytest-cov`, `hypothesis`, `ruff`,
`mypy`

**Storage**: SQLite via stdlib `sqlite3`, append-only enforced by `BEFORE UPDATE`/`BEFORE DELETE`
triggers that `RAISE(ABORT)`. Markdown journals rendered per run for reading. Price snapshots as
CSV in `data/raw/` with SHA-256 manifests in `data/snapshots/`

**Testing**: `pytest`, with `hypothesis` property tests on the risk layer. Risk-layer rejection
paths are written before their guards, per the constitution's workflow section

**Target Platform**: Local CLI on Windows, macOS, and Linux. No server, no service, no network
listener

**Project Type**: Single-project CLI application with a library core

**Performance Goals**: Not performance-sensitive. A ten-year daily backtest (~2,500 bars)
completes in under 10 seconds. Determinism is prioritised over speed everywhere the two conflict —
hence `Decimal` arithmetic throughout the decision path

**Constraints**: Fully offline once a snapshot is pinned. Zero credentials required for the
default daily cadence. Byte-identical journals across repeated runs of the same snapshot and
config. No randomness, no wall-clock reads, and no network I/O anywhere in the decision path

**Scale/Scope**: One instrument, one open position at a time, long or flat. ~2,500–6,000 bars and
a few hundred trades per run. Roughly 2,000–2,500 lines of implementation plus tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Gate | Pre-Phase 0 | Post-Phase 1 |
|---|---|---|---|---|
| I | Capital Preservation First | No order may be constructed outside `RiskGate`; per-trade risk, daily-loss halt, and the forbidden operations (widen stop, remove stop, average down) have no API surface | PASS — design has no order constructor reachable without an `Authorization` | PASS — `Authorization` is mintable only by `RiskGate`; forbidden mutations are absent from the `Position` type, which is frozen |
| II | Gold-Only Scope | Allow-list check in the order path, failing closed; related markets readable but not tradable | PASS | PASS — allow-list is checked inside `RiskGate.authorize`, before any `Authorization` exists |
| III | Every Decision Is Explained | A `Decision` cannot be constructed without verdicts; every principle resolves to a lesson | PASS | PASS — enforced in `Decision.__post_init__`; a test asserts zero orphan principles (SC-010) |
| IV | Simulate Before Risking Money | No live order path in the dependency tree; look-ahead structurally prevented; costs modelled; promotion state recorded | PASS | PASS — `SimulatedBroker` is the only `Broker` implementation; `MarketView` raises on future access |
| V | Reproducible and Auditable | Append-only store; full metric set; secrets from environment; every claim traceable to a run artifact | PASS | PASS — SQLite triggers enforce append-only; `PerformanceReport` has no single-metric accessor |

**Additional constitution requirements addressed in design**

- *Kill switch* (Risk section): `goldbot kill` cancels working orders, flattens simulated
  positions, writes a halt record, and sets a latch file that blocks new entries until cleared.
- *SAFE mode* (Risk section): stale data, fetch failure, or an unhandled exception in the decision
  path halts new entries, preserves the existing stop, and alerts.
- *Lesson pairing* (Workflow section): a test enumerates every `principle` value emitted by any
  rule and asserts a corresponding lesson file exists. Adding a rule without its lesson fails CI.
- *No live credentials in CI*: the default daily path requires no credentials at all, so CI runs
  the full suite offline against committed fixtures.

**One deviation from a literal reading of the spec**, documented rather than silently applied:
FR-021 requires modelling "expense-ratio drag" additively, which would double-count a fee already
embedded in the ETF's share price. The design accounts for it correctly by trading the fund's own
price series and disclosing the ratio in the report. See [research.md](./research.md) R10 — a
wording amendment is recommended via `/speckit-clarify`.

## Project Structure

### Documentation (this feature)

```text
specs/001-explainable-gold-bot/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   ├── cli.md           # Command surface, arguments, exit codes
│   ├── interfaces.md    # Internal seams that must not drift
│   └── records.md       # Durable decision-record and audit schema
├── checklists/
│   └── requirements.md  # Spec quality validation record
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/goldbot/
├── domain/              # Frozen value types. No I/O, no dependencies on other layers.
│   ├── money.py         # Decimal context, Price, Cash, Shares
│   ├── bar.py           # Bar, MarketView (raises on future access)
│   ├── verdict.py       # Verdict — rule id, principle, passed, evidence, statement
│   ├── decision.py      # Decision — constructed from verdicts, refuses to exist without them
│   ├── order.py         # Order, Authorization, Fill
│   └── position.py      # Position, Trade — frozen; no widen/remove/average-down operations
├── data/
│   ├── snapshot.py      # Manifest write, SHA-256 verification, refuse on mismatch
│   ├── sources/         # stooq.py (default, no key), tiingo.py, alpaca_intraday.py (4h only)
│   └── feed.py          # DataFeed protocol; HistoricalFeed and LiveFeed implementations
├── strategy/
│   ├── rules/           # One rule per file; each returns a Verdict
│   ├── indicators.py    # Decimal SMA, ATR, and friends over an explicit bar window
│   └── setup.py         # Ruleset composition; evaluates all rules, never short-circuits
├── risk/
│   ├── gate.py          # RiskGate.authorize — the only source of Authorization
│   ├── sizing.py        # Whole-share sizing; records which constraint bound
│   └── limits.py        # Per-trade risk, daily-loss halt, allow-list, kill-switch latch
├── execution/
│   └── simulated.py     # SimulatedBroker — the only Broker implementation
├── engine/
│   ├── clock.py         # Injected; HistoricalClock and LiveClock
│   └── loop.py          # The single decision loop shared by backtest and paper
├── journal/
│   ├── store.py         # SQLite append-only audit store
│   ├── render.py        # Markdown journal and Rich on-screen output
│   └── report.py        # PerformanceReport — full metric set, no single-metric accessor
├── lessons/
│   ├── content/         # One Markdown lesson per principle id
│   └── review.py        # Closed-trade review notes, principle coverage
└── cli/
    └── main.py          # Typer app: data, backtest, paper, journal, lessons, kill

tests/
├── unit/                # Per-module; risk rejection paths written before their guards
├── integration/         # Full backtest runs, reproducibility, paper session
├── constitution/        # Executable gates: no live SDK, no orphan principles, no wall-clock
└── fixtures/            # Small committed CSVs — deliberately not gitignored

data/
├── raw/                 # Bulk downloads (gitignored)
└── snapshots/           # Manifests: source, symbol, range, row count, SHA-256 (tracked)
```

**Structure Decision**: Single project, layered by dependency direction rather than by technical
kind. `domain/` depends on nothing; `strategy/` and `risk/` depend only on `domain/`; `engine/`
composes them; `cli/` is the only layer allowed to touch the outside world besides `data/sources/`.

The layering is load-bearing rather than decorative: it is what lets
`tests/constitution/` assert architectural facts cheaply — that nothing under `strategy/` or
`risk/` imports `httpx` or `datetime.now`, that no module imports a brokerage SDK, and that the
only `Broker` implementation is the simulated one. Those tests are the enforcement mechanism for
Principles I and IV, so the structure they inspect has to be stable.

`tests/constitution/` is an unusual directory and it is deliberate. Those tests do not check
behaviour; they check that the constitution's non-negotiables remain true as the code grows.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations. All five gates pass at both checkpoints.

One decision deserves a note even though it is not a violation: building a bespoke engine (R1)
rather than adopting a mature backtesting library is more code than the alternative. It is
justified because the explanation requirement inverts the usual priority — the reasoning trace is
the product and the return series is secondary — and because every candidate library would have to
be prised away from the order path to admit the risk gate. The scope that makes this cheap (one
instrument, one position, long-or-flat, daily bars) is fixed by the spec, so the build stays small.
