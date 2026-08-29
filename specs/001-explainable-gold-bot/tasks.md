---

description: "Task list for feature implementation"
---

# Tasks: Explainable Gold Trading Bot

**Input**: Design documents from `/specs/001-explainable-gold-bot/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Included and non-optional. The [constitution](../../.specify/memory/constitution.md)
requires that risk-layer rejection tests be written *before* the guards they cover, and the
architecture depends on a `tests/constitution/` suite that asserts the non-negotiables stay true.
Tasks marked **MUST FAIL FIRST** are red-phase tasks — verify the failure before implementing.

**Organization**: Grouped by user story so each is independently implementable and testable.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Exact file paths included in every task

## Path Conventions

Single project: `src/goldbot/`, `tests/` at repository root, per plan.md.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization

- [X] T001 Create the directory tree from plan.md under `src/goldbot/` and `tests/` (domain, data, strategy, risk, execution, engine, journal, lessons, cli; tests/unit, tests/integration, tests/constitution, tests/fixtures)
- [X] T002 Initialize the uv project in `pyproject.toml` with runtime deps (httpx, exchange_calendars, typer, rich, pandas) and dev deps (pytest, pytest-cov, hypothesis, ruff, mypy); commit `uv.lock`
- [X] T003 [P] Configure ruff and mypy in `pyproject.toml` with strict settings for `src/goldbot/domain/`
- [X] T004 [P] Configure pytest in `pyproject.toml`: test paths, `constitution` marker, coverage thresholds
- [X] T005 [P] Add `.env.example` documenting `ALPACA_API_KEY` / `ALPACA_API_SECRET` as optional and needed only for the 4-hour cadence

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The domain types and the risk layer. Every user story depends on these, and the
constitution's guarantees are enforced here or nowhere.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Domain value types

- [X] T006 Pin a single `decimal.Context` and define Price/Cash/Shares helpers in `src/goldbot/domain/money.py`
- [X] T007 [P] Define the exception hierarchy (`LookAheadError`, `GuardViolation`, `DataIntegrityError`, `HaltRequired`) in `src/goldbot/domain/errors.py`
- [X] T008 [P] Implement `Bar` with OHLC validation and `MarketView` that raises `LookAheadError` past `as_of` in `src/goldbot/domain/bar.py`
- [X] T009 [P] Implement `Verdict` with non-empty statement/evidence/principle validation in `src/goldbot/domain/verdict.py`
- [X] T010 [P] Implement `Instrument` and the allow-list container in `src/goldbot/domain/instrument.py`
- [X] T011 [P] Implement `RiskEnvelope` with content-hash versioning in `src/goldbot/domain/envelope.py`
- [X] T012 Implement `Action`, `Constraint`, `EntryPlan`, and `Decision` — refusing construction without verdicts — in `src/goldbot/domain/decision.py` (depends on T009)
- [X] T013 Implement `Side`, `Costs`, `Authorization` (no public constructor), `Order`, and `Fill` in `src/goldbot/domain/order.py` (depends on T012)
- [X] T014 [P] Implement frozen `Position` and `Trade` with `ExitReason`/`LossClass`, deliberately omitting widen-stop, remove-stop, and add-shares operations, in `src/goldbot/domain/position.py`
- [X] T015 [P] Add small committed OHLCV fixtures covering a trend, a drawdown, a gap-through-stop, and a data gap in `tests/fixtures/`

### Constitution guard tests

- [X] T016 [P] Guard test asserting a rule reaching past the decision bar raises, in `tests/constitution/test_no_lookahead.py`
- [X] T017 [P] Guard test asserting `domain/` imports no other layer, in `tests/constitution/test_layering.py`
- [X] T018 [P] Guard test asserting no wall-clock read is reachable from `strategy/`, `risk/`, or `engine/`, in `tests/constitution/test_no_wallclock.py`
- [X] T019 [P] Guard test asserting no brokerage trading SDK appears in `uv.lock`, in `tests/constitution/test_no_live_broker.py`
- [X] T020 [P] Guard test asserting no I/O or randomness is reachable from `strategy/`, in `tests/constitution/test_rules_are_pure.py`

### Risk layer (TDD — red phase first)

- [X] T021 [P] **MUST FAIL FIRST** — rejection tests for allow-list violation, missing stop, stop on wrong side, oversized risk, widen-stop attempt, and average-down attempt, in `tests/unit/risk/test_rejections.py`
- [X] T022 [P] **MUST FAIL FIRST** — guard test asserting `Authorization` cannot be constructed outside `RiskGate`, in `tests/constitution/test_authorization_unforgeable.py`
- [X] T023 Implement whole-share sizing recording the binding constraint (risk budget vs available cash) in `src/goldbot/risk/sizing.py`
- [X] T024 Implement per-trade risk, concurrent-position, and allow-list limit checks in `src/goldbot/risk/limits.py`
- [X] T025 Implement `RiskGate.authorize` as the sole source of `Authorization`, returning an explanatory `Rejection` on failure, in `src/goldbot/risk/gate.py` (depends on T023, T024)
- [X] T026 [P] Hypothesis property tests asserting sized risk never exceeds the envelope for any price/stop/equity combination, in `tests/unit/risk/test_sizing_properties.py`

### Audit store

- [X] T027 Write the SQLite schema with `BEFORE UPDATE`/`BEFORE DELETE` abort triggers on every record table and `CHECK (simulated = 1)` on orders, in `src/goldbot/journal/schema.sql`
- [X] T028 [P] **MUST FAIL FIRST** — guard test asserting UPDATE and DELETE raise on every record table, in `tests/constitution/test_append_only.py`
- [X] T029 Implement `AuditStore` writers and readers (`record_decision`, `record_fill`, `record_violation`, `decisions_on`) storing decimals as TEXT, in `src/goldbot/journal/store.py`

### Configuration

- [X] T030 Implement config loading into `StrategyConfig`, `RiskEnvelope`, and the instrument allow-list, with content hashing, in `src/goldbot/config.py`
- [X] T031 [P] Write the baseline strategy configuration in `config/baseline.toml`
- [X] T032 [P] Write a deliberately invalid configuration requesting a non-gold symbol, a stopless entry, and an oversized position in `config/violations-probe.toml`

**Checkpoint**: Domain, risk gate, and audit store are in place. User story work can begin.

---

## Phase 3: User Story 1 - Explained Backtest on Historical Gold Data (Priority: P1) 🎯 MVP

**Goal**: Run the strategy over a pinned historical snapshot and produce a decision journal with a
plain-language entry for every bar — including the ones where nothing happened — plus a
performance report net of costs.

**Independent Test**: Point the system at a pinned snapshot with no broker and no live data. Every
decision has an explanation, and the report accounts for spread, commission, and slippage.

### Data pipeline

- [X] T033 [P] [US1] Implement manifest write and SHA-256 verification, refusing on mismatch, in `src/goldbot/data/snapshot.py`
- [X] T034 [P] [US1] Implement the Stooq end-of-day source in `src/goldbot/data/sources/stooq.py`
- [X] T035 [US1] Implement the `DataFeed` protocol, `HistoricalFeed`, and explicit `DataGap` emission without interpolation, in `src/goldbot/data/feed.py` (depends on T033)
- [X] T036 [P] [US1] Integration test asserting a corrupted snapshot exits 3 with the digest named, in `tests/integration/test_snapshot_integrity.py`

### Strategy rules and their lessons

- [X] T037 [P] [US1] Implement Decimal SMA, ATR, and rate-of-change over an explicit bar window in `src/goldbot/strategy/indicators.py`
- [X] T038 [US1] Define the `Rule` protocol and the rule registry in `src/goldbot/strategy/rule.py`
- [X] T039 [P] [US1] Implement the trend filter rule returning a `Verdict` in `src/goldbot/strategy/rules/trend_filter.py`
- [X] T040 [P] [US1] Write the trend-alignment lesson in `src/goldbot/lessons/content/trend-alignment.md`
- [X] T041 [P] [US1] Implement the entry trigger rule in `src/goldbot/strategy/rules/entry_trigger.py`
- [X] T042 [P] [US1] Write the momentum-confirmation lesson in `src/goldbot/lessons/content/momentum-confirmation.md`
- [X] T043 [P] [US1] Implement the ATR-based stop placement rule in `src/goldbot/strategy/rules/atr_stop.py`
- [X] T044 [P] [US1] Write the volatility-based-stops lesson in `src/goldbot/lessons/content/volatility-based-stops.md`
- [X] T045 [P] [US1] Implement the scheduled-event blackout rule in `src/goldbot/strategy/rules/event_blackout.py`
- [X] T046 [P] [US1] Write the event-risk lesson in `src/goldbot/lessons/content/event-risk.md`
- [X] T047 [US1] Implement setup composition that evaluates every rule without short-circuiting in `src/goldbot/strategy/setup.py` (depends on T038–T045)
- [X] T048 [P] [US1] Guard test asserting every principle emitted by a registered rule has a lesson file, in `tests/constitution/test_no_orphan_principles.py`

### Explanation and execution

- [X] T049 [US1] Implement the `Explainer` rendering only from `decision.verdicts`, naming every failed verdict on a SKIP, in `src/goldbot/journal/explain.py`
- [X] T050 [US1] Implement `SimulatedBroker` with spread, commission, and slippage modelling plus gap-through-stop fills recording `risk_overrun`, in `src/goldbot/execution/simulated.py`
- [X] T051 [US1] Implement `HistoricalClock` deriving time from the bar sequence in `src/goldbot/engine/clock.py`
- [X] T052 [US1] Implement the decision loop emitting exactly one `Decision` per completed bar and writing it before acting, in `src/goldbot/engine/loop.py` (depends on T047, T049, T050, T051)

### Reporting

- [X] T053 [P] [US1] Implement the Markdown journal renderer and Rich on-screen output in `src/goldbot/journal/render.py`
- [X] T054 [P] [US1] Implement `PerformanceReport` exposing only the full metric set — expectancy, win rate, average R, max drawdown, trade count, net return, gap-overrun count, disclosed expense ratio — in `src/goldbot/journal/report.py`

### Command line

- [X] T055 [US1] Implement the Typer application, `--version` reporting `execution: simulated only`, and the exit-code mapping from contracts/cli.md, in `src/goldbot/cli/main.py`
- [X] T056 [P] [US1] Implement `data pull` and `data verify` in `src/goldbot/cli/data.py`
- [X] T057 [P] [US1] Implement `backtest` in `src/goldbot/cli/backtest.py`
- [X] T058 [P] [US1] Implement `journal show` and `journal why` in `src/goldbot/cli/journal.py`
- [X] T059 [P] [US1] Implement `report` in `src/goldbot/cli/report.py`

### Story validation

- [X] T060 [P] [US1] Integration test asserting decision count equals evaluated-bar count, in `tests/integration/test_decision_coverage.py`
- [X] T061 [P] [US1] Integration test asserting two runs of the same snapshot and config produce byte-identical journals, in `tests/integration/test_reproducibility.py`
- [X] T062 [P] [US1] Integration test asserting reported costs are non-zero and itemised, in `tests/integration/test_costs_modelled.py`
- [X] T063 [P] [US1] Integration test running `config/violations-probe.toml` and asserting exit 4 with one `violations` row per rejected attempt, in `tests/integration/test_violations_probe.py`

**Checkpoint**: User Story 1 is fully functional. This is the MVP — a system that teaches you the
strategy with zero capital at risk.

---

## Phase 4: User Story 2 - Explained Paper Trading with Enforced Risk Limits (Priority: P2)

**Goal**: Run the same decision loop forward against live data with simulated fills, where the
risk rules are enforced by the system rather than by the operator's discipline.

**Independent Test**: Run a paper session for one trading session. Every simulated order carried a
stop and a correctly derived size, a forced daily-loss breach halts new entries, and the kill
switch flattens everything.

### Promotion gating

- [ ] T064 [P] [US2] Implement the `PromotionState` machine with `LIVE` deliberately undefined, in `src/goldbot/engine/promotion.py`
- [ ] T065 [US2] Implement `walkforward` recording its result against promotion state and refusing paper mode when prerequisites are unmet, in `src/goldbot/cli/walkforward.py`

### Live data and the next-open rule

- [ ] T066 [P] [US2] Wrap `exchange_calendars` for XNYS sessions, holidays, and early closes in `src/goldbot/engine/calendar.py`
- [ ] T067 [US2] Implement `LiveClock` and `next_session_open` in `src/goldbot/engine/clock.py` (depends on T066)
- [ ] T068 [US2] Implement `LiveFeed` returning a `None` digest and polling completed end-of-day bars, in `src/goldbot/data/feed.py`
- [ ] T069 [US2] Implement next-session-open execution recording `slippage_vs_intended` in `src/goldbot/execution/simulated.py`
- [ ] T070 [P] [US2] Integration test asserting a decision on a completed bar fills at the next session open across a weekend and a holiday, in `tests/integration/test_next_open_execution.py`

### Halts and the kill switch

- [ ] T071 [P] [US2] **MUST FAIL FIRST** — tests asserting the daily loss limit blocks new entries, writes a `halts` row, and does not self-clear overnight, in `tests/unit/risk/test_daily_halt.py`
- [ ] T072 [US2] Implement the daily-loss halt with explicit resume in paper mode and recorded next-session resume in backtest mode, in `src/goldbot/risk/limits.py`
- [ ] T073 [P] [US2] **MUST FAIL FIRST** — tests asserting the kill switch flattens, cancels, latches, and is idempotent, in `tests/unit/risk/test_kill_switch.py`
- [ ] T074 [US2] Implement the kill switch and its latch file in `src/goldbot/risk/kill_switch.py`
- [ ] T075 [US2] Implement SAFE mode on stale data, fetch failure, or unhandled decision-path error in `src/goldbot/engine/loop.py`
- [ ] T076 [P] [US2] Integration test asserting SAFE mode blocks entries, preserves the stop, and exits 5, in `tests/integration/test_safe_mode.py`

### Session runner and commands

- [ ] T077 [US2] Implement the paper session runner reusing the US1 decision loop unchanged, in `src/goldbot/engine/paper.py` (depends on T067, T068, T069)
- [ ] T078 [P] [US2] Implement `paper run`, `paper status`, and `paper resume` in `src/goldbot/cli/paper.py`
- [ ] T079 [P] [US2] Implement `kill` and `kill --clear` in `src/goldbot/cli/kill.py`
- [ ] T080 [P] [US2] Add `halts` persistence to `src/goldbot/journal/store.py`

### Story validation

- [ ] T081 [P] [US2] Integration test running a full simulated paper session against fixture bars, in `tests/integration/test_paper_session.py`
- [ ] T082 [P] [US2] Integration test asserting the kill switch completes within 10 seconds, in `tests/integration/test_kill_timing.py`
- [ ] T083 [P] [US2] Guard test asserting no network I/O is reachable from `execution/`, in `tests/constitution/test_no_network_in_execution.py`

**Checkpoint**: User Stories 1 and 2 both work independently.

---

## Phase 5: User Story 3 - Trading Principles Curriculum Tied to Real Decisions (Priority: P3)

**Goal**: Turn a stream of per-decision justifications into cumulative understanding — lessons,
closed-trade review notes, and a view of which principles the market has actually shown you.

**Independent Test**: Using only a completed backtest journal, open a decision, follow it to its
lesson, and read the closed-trade review note. Check the coverage view. No live data required.

- [ ] T084 [US3] Implement the lesson loader with front-matter validation and principle-id resolution in `src/goldbot/lessons/loader.py`
- [ ] T085 [P] [US3] Expand every lesson with its failure modes and gold-specific behaviour sections in `src/goldbot/lessons/content/`
- [ ] T086 [P] [US3] Implement loss classification into `CORRECT`, `RULE_VIOLATION`, and `SYSTEM_ERROR` in `src/goldbot/lessons/classify.py`
- [ ] T087 [US3] Implement review-note generation contrasting entry expectation with outcome in `src/goldbot/lessons/review.py` (depends on T086)
- [ ] T088 [US3] Implement principle coverage — encounters, trades taken, win rate per principle — in `src/goldbot/lessons/coverage.py`
- [ ] T089 [P] [US3] Add `review_notes` persistence to `src/goldbot/journal/store.py`
- [ ] T090 [P] [US3] Implement `lessons list`, `lessons show`, `lessons coverage`, and `lessons review` in `src/goldbot/cli/lessons.py`
- [ ] T091 [P] [US3] Add the loss-classification breakdown to the report output in `src/goldbot/journal/report.py`
- [ ] T092 [P] [US3] Integration test asserting every closed trade produces a review note, in `tests/integration/test_review_notes.py`
- [ ] T093 [P] [US3] Unit test asserting coverage counts match the journal, in `tests/unit/lessons/test_coverage.py`
- [ ] T094 [P] [US3] Unit test asserting a rule-violation loss is never classified as correct, in `tests/unit/lessons/test_classification.py`
- [ ] T095 [P] [US3] Unit test asserting every lesson has all four required sections, in `tests/unit/lessons/test_lesson_content.py`

**Checkpoint**: All three user stories are independently functional.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T096 [P] Implement the 4-hour cadence with an explicit labelled-partial-bar policy in `src/goldbot/data/feed.py`
- [ ] T097 [P] Implement the Alpaca intraday data source, data-only with no trading client, in `src/goldbot/data/sources/alpaca_intraday.py`
- [ ] T098 [P] Implement the Tiingo end-of-day source as a keyed alternative in `src/goldbot/data/sources/tiingo.py`
- [ ] T099 [P] Implement credential loading from environment with no fallback to file or literal, in `src/goldbot/config.py`
- [ ] T100 [P] Guard test asserting no credential value can appear in any audit record or log line, in `tests/constitution/test_no_secrets_logged.py`
- [ ] T101 [P] Emit a startup warning when equity is low enough that whole-share rounding makes the 1% rule approximate, in `src/goldbot/cli/main.py`
- [ ] T102 [P] Add expense-ratio disclosure and the IEX-data caveat for 4-hour mode to report output in `src/goldbot/journal/report.py`
- [ ] T103 [P] Update `README.md` — mark plan and tasks complete, add install and usage sections, correct the repository layout
- [ ] T104 [P] Bring ruff and mypy to clean across `src/` and `tests/`
- [ ] T105 Run the full `quickstart.md` validation, all seven scenarios, end to end
- [ ] T106 [P] Write the operator guide in `docs/operating.md`
- [ ] T107 [P] Add the offline CI workflow running the full suite against committed fixtures in `.github/workflows/ci.yml`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies
- **Foundational (Phase 2)**: Depends on Setup — **blocks all user stories**
- **User Story 1 (Phase 3)**: Depends on Foundational only
- **User Story 2 (Phase 4)**: Depends on Foundational. Reuses the US1 decision loop, so in
  practice it follows US1 rather than running truly parallel to it
- **User Story 3 (Phase 5)**: Depends on Foundational. Needs *a* journal to read but not
  necessarily a live one — it can be built against US1's backtest output alone
- **Polish (Phase 6)**: Depends on the stories being delivered

### User Story Dependencies

- **US1 (P1)**: Independent. Delivers the MVP
- **US2 (P2)**: Shares the engine with US1. Independently *testable* — a paper session proves
  itself — but not independently *buildable* without the loop US1 creates
- **US3 (P3)**: Independent of US2 entirely. Consumes decision records, which US1 produces

### Within Each Story

- Red-phase tests (**MUST FAIL FIRST**) before their implementations
- Domain types before the services that compose them
- Rules before setup composition
- Engine before CLI

### Parallel Opportunities

- T003–T005 in Setup
- T007–T011 and T014–T015 in Foundational — six domain modules, six different files
- T016–T020 — the entire guard-test suite
- T039–T046 in US1 — four rules and their four lessons, eight separate files
- T060–T063 — all four US1 validation tests
- T084–T095 in US3 — most of the story, once the loader lands
- Nearly all of Phase 6

---

## Parallel Example: User Story 1 Rules

```bash
# Four rules and their paired lessons — eight files, no shared state:
Task: "Implement the trend filter rule in src/goldbot/strategy/rules/trend_filter.py"
Task: "Write the trend-alignment lesson in src/goldbot/lessons/content/trend-alignment.md"
Task: "Implement the entry trigger rule in src/goldbot/strategy/rules/entry_trigger.py"
Task: "Write the momentum-confirmation lesson in src/goldbot/lessons/content/momentum-confirmation.md"
Task: "Implement the ATR-based stop placement rule in src/goldbot/strategy/rules/atr_stop.py"
Task: "Write the volatility-based-stops lesson in src/goldbot/lessons/content/volatility-based-stops.md"
Task: "Implement the scheduled-event blackout rule in src/goldbot/strategy/rules/event_blackout.py"
Task: "Write the event-risk lesson in src/goldbot/lessons/content/event-risk.md"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup
2. Phase 2: Foundational — the risk gate and the guard tests are the point of this phase, not
   scaffolding to rush through
3. Phase 3: User Story 1
4. **STOP and VALIDATE**: run quickstart Scenarios 1–4
5. At this point you have a system that teaches you the strategy with no capital at risk. It is a
   legitimate stopping point if paper trading can wait

### Incremental Delivery

1. Setup + Foundational → the guarantees exist before any strategy code does
2. US1 → explained backtest → validate → **MVP**
3. US2 → paper trading with enforced limits → validate
4. US3 → curriculum → validate
5. Polish → 4-hour cadence, alternative data sources, docs

### Suggested Commit Grouping

Commit after each task or tight group. Two groups deserve their own commits regardless of size:
the red-phase test tasks (so the failure is in the history) and each guard test (so it is obvious
when one was added or weakened).

---

## Notes

- **[P]** = different files, no dependencies. **[Story]** maps a task to its user story.
- Verify red-phase tests actually fail before implementing against them. A test that passes on an
  empty implementation is testing nothing.
- **Two domain modules beyond plan.md's tree**: `domain/instrument.py` and `domain/envelope.py`.
  The plan's listing was illustrative; these are ordinary refinements, not scope changes.
- **Daily-loss halt semantics differ by mode.** In paper mode it requires explicit operator resume
  per the constitution. In backtest mode there is no operator, so T072 records the halt and
  resumes at the next session — a simulation of the operator returning the following day. Both
  behaviours are recorded in `halts`; neither silently ignores the limit.
- **FR-021 is implemented per research.md R10**, not literally: the expense ratio is inherited
  from the ETF's own price series and disclosed, never applied a second time as a cost. If
  `/speckit-clarify` reworks that requirement, T054 and T102 are the tasks affected.
- The four rules in US1 (T039–T046) are a reasonable starting strategy, not a validated edge.
  Principle IV governs what happens next: they earn promotion through walk-forward and paper, or
  they get replaced. The framework is the deliverable; the specific rules are swappable by design.
