# Phase 0 Research: Explainable Gold Trading Bot

**Feature**: 001-explainable-gold-bot | **Date**: 2026-08-21

Every decision below traces to a requirement in [spec.md](./spec.md) or a principle in the
[constitution](../../.specify/memory/constitution.md). Where a finding contradicts the spec, it is
flagged rather than quietly worked around.

## R1. Backtest engine: build rather than adopt

**Decision**: Write a small event-driven engine rather than adopt backtesting.py, vectorbt,
backtrader, or nautilus_trader.

**Rationale**: The product requirement is not "compute a return series" — it is FR-001 through
FR-008, that every evaluation emits the reasoning that actually drove it. Vectorised libraries
compute signals as array operations, so the "why" for a single bar has to be reconstructed after
the fact, which the spec explicitly forbids ("Explanations are generated from the strategy's own
rule structure, not by an external narrator inspecting results after the fact"). Event-driven
libraries come closer but still own the order path, and FR-012 requires a risk gate that can
reject an order before anything sees it.

The scope also makes the build cheap: one instrument, one open position, long-or-flat, daily bars.
A decade of daily bars is roughly 2,500 iterations of a simple loop. The engine that satisfies
these requirements is smaller than the adapter needed to bend a library into satisfying them.

**Alternatives considered**: backtesting.py — clean API, but signals are vectors and the order
model is fixed. vectorbt — fastest, entirely wrong shape for per-decision narration.
nautilus_trader — genuinely excellent and event-driven, but it is a large system aimed at live
multi-venue trading, and its order pipeline is the part we specifically need to own.

## R2. Explanations as structure, not commentary

**Decision**: Every rule returns a `Verdict` — rule id, principle, pass/fail, the evidence values
used, and a one-line human statement. A `Decision` is constructed *from* its verdicts and cannot
exist without them. Orders can only be created from a `Decision`.

**Rationale**: This turns FR-006 ("block any order for which an explanation cannot be produced")
from a runtime check into a structural impossibility — there is no code path that produces an
order without the reasoning attached, because the reasoning is the constructor argument. It
likewise satisfies FR-007: an opaque signal source cannot mint a `Verdict`, so it cannot reach the
order path.

**Consequence — rules do not short-circuit.** All rules in a setup are evaluated even after one
fails. Boolean short-circuiting would be marginally faster and would destroy FR-004: to explain a
skipped setup you need to know which conditions *passed* as well as the one that did not. Full
evaluation is the deliberate choice.

**Alternatives considered**: Logging explanation strings alongside the logic — the standard
approach, and it drifts the first time someone edits a condition without editing its message.
Generating narration from an LLM after the run — flatly incompatible with the spec, and it would
invent plausible reasoning rather than report actual reasoning.

## R3. Paper execution: simulate locally, never transmit

**Decision**: Fills are simulated in-process by a `SimulatedBroker`. No brokerage trading client
is installed as a dependency at all.

**Rationale**: Alpaca is the obvious paper-trading candidate — free paper accounts, $100k virtual
balance, US equities and ETFs, and "the paper trading API has the same interface as the live
trading API, making it easy to switch between the two"
([Alpaca docs](https://docs.alpaca.markets/us/docs/paper-trading)). That last property is exactly
what FR-024 prohibits: a system one base-URL edit away from live money. The spec's own wording for
User Story 2 is "live gold market data with **simulated fills**", which points the same way.

Simulating locally makes FR-024 testable by absence: a test asserts that no brokerage trading SDK
appears in the dependency lock and that no module in the order path performs network I/O. "No live
path exists" is verifiable; "live path disabled by a flag" is not.

**Alternatives considered**: Alpaca paper endpoint — rejected above, though it remains the natural
choice for the future live feature, where the gating work happens deliberately. IBKR paper —
same objection plus a much heavier integration.

## R4. Market data: one source for both backtest and paper

**Decision**: Use a single end-of-day source for both the backtest and the daily-cadence paper
session. Stooq as the default (no API key, free, permits personal non-commercial use), Tiingo as a
keyed alternative for anyone who wants documented terms and cleaner data.

**Rationale**: Using different sources for research and paper trading reintroduces exactly the
train/serve skew FR-036 exists to prevent — the same day's bar can differ between vendors by a
cent, and the strategy would be validated on prices it will never trade against. One source for
both removes the class of bug entirely.

A useful consequence: **the default daily path needs no credentials at all.** Stooq is an
unauthenticated CSV endpoint, so the whole v1 default configuration runs with zero secrets. The
secrets handling required by FR-028 still gets built, but it is exercised only by the optional
4-hour mode (R5).

yfinance was rejected for anything load-bearing: Yahoo's backend has broken repeatedly and the
maintainers patch reactively, so it is widely treated as unsuitable for production use
([data card](https://edwardlg.github.io/assip-2026-empirical-finance/textbook/data-cards/free-equity-apis.html)).
It remains fine as a manual cross-check when validating a snapshot.

**Pinning**: data is fetched once into `data/raw/`, hashed with SHA-256, and described by a
manifest in `data/snapshots/` recording source, symbol, date range, row count, and digest. The
loader verifies the digest before every run and refuses to proceed on a mismatch. This is what
makes FR-020 reproducibility real, and it matches the `.gitignore` split already in the repo —
manifests tracked, bulk data not.

## R5. The 4-hour bar problem

**Decision**: Daily is the default and the only cadence with a no-credential path. The 4-hour mode
is configurable, requires an intraday source (Alpaca's free Basic tier, IEX-only), and must
declare its partial-bar policy explicitly.

**Rationale**: A regular US equity session is 6.5 hours, which yields one full 4-hour bar plus a
2.5-hour remainder — FR-034 requires this be handled openly rather than by emitting a short bar as
though it were complete. The policy chosen: the remainder is a **labelled partial bar** that the
engine may read for context but may not treat as a completed bar for decision purposes. Only
completed bars trigger decisions, per Principle IV.

The IEX-only limitation of Alpaca's free tier is worth recording: IEX carries a minority of
consolidated volume, so intraday prints can deviate from the consolidated tape. Acceptable for a
simulated learning system; must be disclosed in any performance report produced in 4-hour mode.

## R6. Exchange calendar and the next-open rule

**Decision**: Use `exchange_calendars` for XNYS sessions, half-days, and holidays.

**Rationale**: FR-038 requires a decision made on a completed daily bar to execute at the next
session's open. "Next session" is not "tomorrow" — it steps over weekends, market holidays, and
1:00 pm early closes. Hand-rolling this produces silent off-by-one-day errors in the backtest that
are almost impossible to spot in aggregate results. All timestamps stored UTC per the
constitution; the calendar owns the exchange-local reasoning.

## R7. Determinism strategy

**Decision**: Four measures, each independently testable.

1. **`Decimal` throughout the decision path**, with a single pinned `decimal.Context`. Prices,
   cash, share counts, risk, and P&L are exact. At a few thousand bars per run the performance
   cost is irrelevant, and it eliminates float-accumulation drift as a source of irreproducibility.
2. **No wall-clock access in the decision path.** The clock is injected; the historical clock is
   derived from the bar sequence. A test asserts the strategy and risk modules never import
   `datetime.now`.
3. **No randomness anywhere.** Not seeded — absent. A test asserts `random` and `numpy.random` are
   unreachable from the engine.
4. **A reproducibility test**: run the same snapshot and config twice, assert the two decision
   journals hash identically (SC-004).

## R8. Look-ahead prevention as a runtime guarantee

**Decision**: Rules receive a `MarketView` — a bounded window ending at the decision bar. Indexing
past the decision bar raises rather than returning data.

**Rationale**: FR-022 demands the system "detect and refuse configurations that would use future
information." Code review cannot guarantee this; a data structure can. A rule that tries to peek
at tomorrow's close fails loudly in a unit test rather than quietly producing an excellent,
untradeable backtest. This is the single most common way a backtest lies, so it is worth spending
a type on.

## R9. Audit storage

**Decision**: SQLite (stdlib `sqlite3`) as the append-only store, with `BEFORE UPDATE` and
`BEFORE DELETE` triggers that `RAISE(ABORT)` on the record tables. Human-readable Markdown
journals are rendered from it per run.

**Rationale**: FR-025 requires an append-only record; triggers make "append-only" a property of
the database rather than a convention developers remember. FR-027 requires retrieving any past
decision by date, which is a query, not a file scan. SQLite is stdlib, single-file, trivially
backed up, and needs no service. The Markdown journal exists because the audit store is for
machines and SC-007 ("answer why in under a minute") is for a human.

## R10. Cost model — and a spec wording problem

**Decision**: Model commission, spread, and slippage explicitly. Do **not** add expense-ratio drag
on top of the price series.

**Rationale, and the flag**: FR-021 currently reads "System MUST model spread, commission,
slippage, and the fund's expense-ratio drag across the holding period." Modelling the fee
additively would double-count it. A physically-backed gold ETF pays its fee by selling gold, so
the drag is already inside the ETF's own share price — which is the series being backtested per
FR-036. Adding it again would understate returns by roughly the expense ratio per year held.

The correct reading is that the expense ratio must be **accounted for**, and it is — automatically
and exactly — by trading the ETF's own price series rather than spot gold. The report should
disclose the fund's expense ratio and state that it is inherited from the price series.

**Recommended spec amendment**: reword FR-021 to "...and MUST account for the fund's expense
ratio, which is inherited from the ETF's own price series and MUST NOT be applied a second time."
Logged here rather than edited unilaterally, since spec changes belong to `/speckit-clarify`.

## R11. Whole-share sizing versus the 1% rule

**Decision**: `shares = min(floor(risk_budget / stop_distance), floor(available_cash /
entry_price))`, with the binding constraint recorded in the decision record. Zero shares produces
a skip with an explanation, never a silent no-op.

**Rationale**: Two constraints compete and either can bind first. A tight stop makes the risk
budget permissive but consumes cash — a $10,000 account risking 1% ($100) with a $3 stop wants 33
shares, which at a ~$300 share price costs $9,900 of the $10,000 available. The cash constraint
binds, and the operator deserves to be told which one did.

**A finding worth stating plainly**: below roughly $5,000 of equity, whole-share quantisation
makes the 1% rule approximate at best — a single share can represent several percent of the
account. This is a property of the instrument choice, not a defect. It should be surfaced at
startup rather than discovered in a confusing journal entry.

## R12. Language, runtime, and tooling

**Decision**: Python 3.11+ (3.11.8 is installed locally), managed by uv 0.11.31 with a committed
lockfile.

Runtime dependencies, deliberately few:

| Package | Purpose | Why not stdlib |
|---|---|---|
| `httpx` | Fetching data snapshots | Modern, timeouts by default |
| `exchange_calendars` | Session, holiday, and half-day logic | See R6; hand-rolling this is a bug farm |
| `typer` | CLI surface | Argument parsing with typed commands |
| `rich` | Readable on-screen decision output | The teaching output is the product (US1, US3) |
| `pandas` | Snapshot I/O and validation only | Used at the boundary; converted to immutable `Bar` objects before the engine sees anything |

Dev: `pytest`, `pytest-cov`, `hypothesis` (property tests for the risk layer), `ruff`, `mypy`.

**Rationale**: pandas is confined to the I/O edge on purpose. The engine operates on a tuple of
frozen `Bar` dataclasses, which keeps the decision path explicit, readable, and deterministic —
and readability is a product requirement here, not a preference, because the operator is meant to
learn from this code.

No numpy in the decision path. No ML libraries: FR-007 bars any component that cannot explain
itself, which rules out the usual suspects by construction.

## Open items carried into design

| Item | Disposition |
|---|---|
| FR-021 expense-ratio double-count | Flagged in R10; recommend `/speckit-clarify` reword. Design implements the correct reading. |
| Which specific ETF | Deferred to configuration, not code. The allow-list is data; planning does not need to name the fund. |
| Broker-resident stops | Out of scope per spec; simulated stops are explicitly an approximation, disclosed in the report. |
| Minimum viable account size | Surface a startup warning below ~$5,000 equity (R11). |

## Sources

- [Alpaca — Paper Trading docs](https://docs.alpaca.markets/us/docs/paper-trading)
- [Alpaca — About Market Data API](https://docs.alpaca.markets/us/docs/about-market-data-api)
- [Free equity price APIs data card — yfinance / Stooq / Tiingo / Alpha Vantage](https://edwardlg.github.io/assip-2026-empirical-finance/textbook/data-cards/free-equity-apis.html)
- [Awesome financial data APIs — 2026 availability status](https://github.com/jeff3388/awesome-financial-data-apis)
