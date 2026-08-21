# Feature Specification: Explainable Gold Trading Bot

**Feature Branch**: `001-explainable-gold-bot`

**Created**: 2026-08-21

**Status**: Draft

**Input**: User description: "a gold trading bot that explains every trade decision"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explained Backtest on Historical Gold Data (Priority: P1)

The operator points the system at a fixed snapshot of historical gold price data and runs the
strategy over it. When the run finishes, they receive two things: a decision journal containing a
plain-language entry for every decision the system made — including the bars where it deliberately
did nothing — and an honest performance report that nets out trading costs.

The operator reads the journal top to bottom and can follow the strategy's reasoning like a
narrated replay: what the market was doing, what condition triggered, why the trade was sized the
way it was, where the idea would have been proven wrong, and what actually happened.

**Why this priority**: This is the smallest slice that delivers both halves of the project's
purpose — a working trading strategy and an education in why it does what it does — while risking
no capital. It is also the gate that every later stage depends on: the constitution forbids paper
trading a strategy that has not passed a reproducible backtest.

**Independent Test**: Run the system against a pinned historical gold data snapshot with no broker
connection and no live data. Read the resulting journal and performance report. The slice succeeds
if every decision in the run has an explanation and the report accounts for spread, commission,
and slippage.

**Acceptance Scenarios**:

1. **Given** a pinned snapshot of historical gold data and a strategy configuration, **When** the
   operator runs a backtest, **Then** the system produces a decision journal with one entry per
   evaluated bar and a performance report covering the full period.
2. **Given** a completed backtest, **When** the operator opens any single entry decision,
   **Then** it states the evidence that triggered it, the trading principle applied, the stop
   level, the position size and the risk taken, and the reward-to-risk ratio accepted.
3. **Given** a bar where no trade was taken, **When** the operator opens that journal entry,
   **Then** it names the specific condition that was missing or the filter that vetoed the setup.
4. **Given** the same data snapshot and the same configuration, **When** the backtest is run a
   second time, **Then** the decision journal is identical to the first run.
5. **Given** a completed backtest, **When** the operator views the performance report, **Then** it
   presents expectancy, win rate, average R multiple, maximum drawdown, and trade count together,
   with all figures net of modelled costs.
6. **Given** a strategy configuration whose rules would have used information not available at
   decision time, **When** the backtest runs, **Then** the system refuses the run and reports the
   look-ahead violation.

---

### User Story 2 - Explained Paper Trading with Enforced Risk Limits (Priority: P2)

The operator runs the system against live gold market data with simulated fills. As the session
progresses, each decision appears in real time with its explanation, and the risk rules are
enforced by the system rather than by the operator's discipline: no order is placed without a stop
and a size derived from that stop, the session halts new entries when the daily loss limit is
reached, and a single command flattens everything.

**Why this priority**: Backtests flatter strategies. Paper trading against live data exposes the
gap between the historical simulation and real market behaviour — spreads that widen, data that
arrives late, sessions that behave differently — while still risking nothing. It is also the first
stage where the risk machinery is exercised against events arriving in real time.

**Independent Test**: Run a paper session against live gold data for one full trading session.
Verify that every simulated order carried a stop and a correctly derived size, that a forced
breach of the daily loss limit halts new entries, and that the kill switch flattens all positions
and cancels all working orders.

**Acceptance Scenarios**:

1. **Given** a live paper session, **When** the strategy generates an entry signal, **Then** the
   decision and its explanation are recorded before the simulated order is transmitted.
2. **Given** a signal whose stop distance would require risking more than the configured
   per-trade limit, **When** the system sizes the position, **Then** the size is reduced to
   respect the limit, or the trade is rejected if the minimum tradable size still exceeds it, and
   the journal records which occurred and why.
3. **Given** an open paper position, **When** cumulative session loss reaches the daily loss
   limit, **Then** the system blocks new entries, records the halt with its reason, and requires
   explicit operator action to resume.
4. **Given** any state of the system, **When** the operator triggers the kill switch, **Then** all
   working orders are cancelled, all positions are flattened, new entries are blocked, and the
   action is recorded in the audit log.
5. **Given** a running session, **When** the market data feed goes stale or the connection drops,
   **Then** the system enters a safe state that places no new entries, leaves existing protective
   stops in force, and alerts the operator.
6. **Given** an open position, **When** any component attempts to widen the stop, remove the stop,
   or add to the losing position, **Then** the attempt is rejected and logged as a violation.

---

### User Story 3 - Trading Principles Curriculum Tied to Real Decisions (Priority: P3)

Every explanation names the trading principle it applies, and each named principle links to a
short lesson: what the concept is, when it works, when it fails, and what it looks like in gold
specifically. After a trade closes, the operator is prompted with a review note comparing what was
expected to what happened. Over time the operator can see which concepts they have actually
encountered in the market and which remain theoretical.

**Why this priority**: Per-decision explanations teach tactically but leave the operator with
scattered fragments. The curriculum layer turns a stream of justifications into cumulative
understanding, which is the second half of the project's purpose. It depends on decisions already
existing, so it follows the stories that produce them.

**Independent Test**: Using only the journal from a completed backtest, open a decision, follow it
to its lesson, and complete a closed-trade review note. Check the concept coverage view. No live
data or broker connection is required.

**Acceptance Scenarios**:

1. **Given** any decision record, **When** the operator follows the named principle, **Then** a
   lesson is shown explaining the concept, its failure modes, and its behaviour in gold.
2. **Given** a closed trade, **When** the operator opens its review note, **Then** the note
   contrasts the expectation recorded at entry with the actual outcome and states whether the
   result supports or contradicts the principle applied.
3. **Given** a completed run, **When** the operator views concept coverage, **Then** the system
   shows which principles have appeared in real decisions and how often.
4. **Given** a run containing losing trades, **When** the operator reviews them, **Then** losses
   correctly taken according to the rules are distinguished from losses caused by rule violations
   or errors.

---

### Edge Cases

- **Missing or gapped price data**: a bar is absent, arrives out of order, or duplicates an
  earlier timestamp. The system must not silently interpolate; it must record the gap and treat
  affected decisions as invalid rather than trading on a fabricated price.
- **Stale data during an open position**: prices stop updating while exposed. New entries stop,
  but the broker-side stop must remain the protection of record.
- **Explanation generation fails**: if the system cannot articulate why it is about to act, the
  order must be blocked, not placed silently. An unexplainable decision is a defect, not a trade.
- **Daily loss limit reached while a position is open**: the halt applies to new entries; the open
  position's existing exit plan still governs it.
- **Conflicting simultaneous signals**: two rules fire in opposite directions on the same bar. The
  system must resolve deterministically by a stated precedence rule and explain the resolution.
- **A non-gold symbol appears in configuration**: rejected outright and logged, with no partial
  execution.
- **Scheduled high-impact event** (rate decision, inflation print, employment report): the
  configured policy applies — trade, reduce size, or stand aside — and the journal names the event
  as the reason.
- **Overnight and weekend gaps**: the exchange is closed for roughly two thirds of every weekday
  and all weekend, so a swing position routinely spans a break. When the market reopens beyond the
  stop, the realised loss exceeds the planned risk. The journal must record the gap and the
  overrun, and performance must be judged including these overruns rather than assuming the stop
  price was obtained.
- **Exchange halt or circuit breaker**: trading is suspended while a position is open and no exit
  is possible at any price until it resumes.
- **ETF dislocation from spot gold**: the fund's share price diverges from the metal, or gold
  moves substantially while the exchange is closed. Context drawn from spot gold must never be
  mistaken for a tradable price.
- **Insufficient cash or whole-share rounding**: the risk-derived size rounds to zero shares, or
  the position cost exceeds available cash. The system must decline the trade and say which
  constraint bound.
- **Partial fill**: the position established is smaller than intended. Risk is recalculated
  against the actual filled size, and the discrepancy is recorded.
- **Duplicate or replayed broker messages**: the same fill reported twice must not be counted
  twice.
- **Clock and session boundaries**: daylight-saving shifts and exchange session changes must not
  move the daily loss window or session filters unintentionally.
- **Configuration changed mid-run**: risk limits must not be alterable while a session is live;
  changes require a documented restart.

## Requirements *(mandatory)*

### Functional Requirements

**Decision explanation**

- **FR-001**: System MUST produce a decision record for every evaluation of the market, including
  evaluations that result in no trade.
- **FR-002**: Every decision record MUST state, in plain language, the evidence that triggered it,
  the named trading principle applied, and the conclusion reached.
- **FR-003**: Every entry decision MUST state the invalidation level (the price at which the idea
  is proven wrong), the position size, the monetary and percentage risk accepted, and the
  reward-to-risk ratio.
- **FR-004**: Every no-trade decision MUST name the specific condition that was absent or the
  filter that vetoed the setup.
- **FR-005**: Every exit decision MUST state which exit rule fired and the realised outcome
  against the expectation recorded at entry.
- **FR-006**: System MUST block any order for which an explanation cannot be produced, and MUST
  record the block as a defect requiring investigation.
- **FR-007**: System MUST NOT grant order-placing authority to any signal source that cannot
  produce a human-readable attribution for its output.
- **FR-008**: Explanations MUST be written for a reader who does not know the strategy's internals
  — no bare indicator values without stated meaning.

**Gold-only scope**

- **FR-009**: System MUST restrict all order placement to instruments on an explicit gold
  allow-list.
- **FR-010**: System MUST reject and log any order for a symbol absent from the allow-list, with
  no partial execution.
- **FR-011**: System MAY consume related markets (dollar index, real yields, silver, gold miners,
  volatility measures) as inputs but MUST NOT place orders in them.

**Risk enforcement**

- **FR-012**: System MUST reject any order that lacks a predetermined stop level or a position
  size derived from that stop.
- **FR-013**: System MUST size every position so that the loss at the stop does not exceed the
  configured per-trade risk limit, and MUST reject the trade when the smallest tradable size would
  exceed that limit.
- **FR-014**: System MUST halt new entries when cumulative session loss reaches the configured
  daily loss limit, and MUST require explicit operator action to resume.
- **FR-015**: System MUST refuse any attempt to widen a stop after entry, remove a stop, or add to
  a losing position, and MUST record each attempt as a violation.
- **FR-016**: System MUST provide a kill switch that cancels all working orders, flattens all
  positions, and blocks new entries until manually cleared.
- **FR-017**: System MUST enter a safe state — no new entries, existing protective stops left in
  force, operator alerted — on stale market data, lost broker connection, or an unhandled error in
  the decision path.
- **FR-018**: System MUST NOT permit risk limits to be changed while a trading session is running.
- **FR-019**: System MUST apply a configured policy for scheduled high-impact economic events and
  MUST name the event in the decision record when the policy affects a decision.

**Simulation and promotion**

- **FR-020**: System MUST support running a strategy over a pinned historical data snapshot and
  MUST produce identical results for identical snapshot and configuration.
- **FR-021**: System MUST model spread, commission, slippage, and the fund's expense-ratio drag
  across the holding period in all simulated results, and MUST NOT report frictionless results as
  performance.
- **FR-022**: System MUST make decisions only from information available at decision time and MUST
  detect and refuse configurations that would use future information.
- **FR-023**: System MUST record which promotion stage a strategy has reached (backtest,
  walk-forward, paper, live) and MUST refuse promotion to a stage whose prerequisites are unmet.
- **FR-024**: System MUST NOT contain any path capable of transmitting an order to a live
  brokerage account. All order placement in this version is simulated; live execution requires a
  subsequent, separately specified feature.

**Audit and reporting**

- **FR-025**: System MUST persist every signal, decision, order, fill, rejection, configuration
  version, and data snapshot reference to an append-only record with UTC timestamps.
- **FR-026**: System MUST report performance as a set including expectancy, win rate, average R
  multiple, maximum drawdown, and trade count, and MUST NOT present any of these figures alone.
- **FR-027**: System MUST allow the operator to retrieve the full reasoning for any past decision
  by date and instrument.
- **FR-028**: System MUST load broker and data credentials from the environment or a secret store
  and MUST NOT write them to any log or record.

**Learning layer**

- **FR-029**: System MUST link every named trading principle in a decision record to a lesson
  covering the concept, its failure modes, and its behaviour in gold specifically.
- **FR-030**: System MUST generate a review note for every closed trade contrasting the entry
  expectation with the actual outcome.
- **FR-031**: System MUST distinguish losses taken correctly according to the rules from losses
  caused by rule violations or system errors.
- **FR-032**: System MUST show which trading principles have appeared in real decisions and how
  frequently.

**Instrument, cadence, and delivery scope**

- **FR-033**: System MUST trade gold exclusively as shares in a physically-backed gold ETF held in
  a cash account. The allow-list contains ETF share symbols only; gold futures, spot XAU/USD,
  contracts for difference, options, and leveraged or inverse gold products are excluded.
- **FR-034**: System MUST evaluate the market on completed daily bars as its default cadence, and
  MUST support 4-hour bars as a configurable alternative. Because a regular exchange session is
  shorter than two four-hour periods, the system MUST define and document how it handles the
  partial final bar rather than silently emitting an incomplete bar as though it were complete.
- **FR-035**: The first delivered version MUST cover User Stories 1 through 3 — explained
  backtest, explained paper trading with enforced risk limits, and the principles curriculum. It
  MUST NOT include live execution.
- **FR-036**: System MUST derive both its signals and its execution levels from the traded ETF's
  own price series. Related markets, including spot gold itself, MAY inform context but MUST NOT
  supply the prices used for entry, stop, or exit levels.
- **FR-037**: System MUST take long or flat positions only. Short exposure, whether by borrowing
  shares or through inverse products, is out of scope.
- **FR-038**: Where a decision is reached on a completed bar while the market is closed, the
  system MUST execute at the next session's open and MUST record the difference between the price
  that triggered the decision and the price actually obtained.

### Key Entities

- **Instrument**: A gold ETF share symbol on the allow-list. Carries its cost profile, exchange
  trading hours, and expense-ratio drag.
- **Market Bar**: One period of price history for an instrument — open, high, low, close, volume,
  and timestamp — sourced from a versioned data snapshot or a live feed.
- **Signal**: A raw observation produced by a rule or indicator, with the evidence that produced
  it. Has no authority to place orders on its own.
- **Decision Record**: The central artifact. One per market evaluation, recording the timestamp,
  the market context, the signals considered, the principle applied, the outcome (enter, exit,
  hold, or skip), the plain-language explanation, and — for entries — the invalidation level,
  size, risk, and reward-to-risk ratio.
- **Order**: An instruction to the broker, always paired with a protective stop and a size derived
  from it. Links back to the decision record that authorised it.
- **Fill**: A broker-confirmed execution, with actual price, size, and realised slippage against
  the intended price.
- **Position**: An open exposure in a gold instrument, with entry, stop, target, current risk, and
  the decision record that opened it.
- **Trade**: A completed round trip from entry to exit, with realised result expressed in both
  currency and R multiples.
- **Risk Envelope**: The binding limits — per-trade risk, daily loss limit, maximum leverage,
  maximum concurrent positions — versioned and immutable during a running session.
- **Run Artifact**: The complete record of one backtest, walk-forward, or paper session — data
  snapshot reference, configuration version, decision journal, and performance report —
  sufficient to reproduce the run.
- **Performance Report**: The honest metric set for a run, net of all modelled costs.
- **Lesson**: An explanation of one trading principle — what it is, when it works, when it fails,
  and how it behaves in gold.
- **Review Note**: A post-trade reflection linking a closed trade to the expectation recorded at
  entry and the principle it confirms or contradicts.
- **Promotion State**: Which stage a strategy has reached and the recorded evidence that its
  acceptance criteria were met.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of market evaluations in any run produce a decision record; zero decisions —
  including no-trade decisions — are unexplained.
- **SC-002**: Given twenty randomly sampled entry decisions, a reader unfamiliar with the strategy
  can correctly state the reason for the trade and where it would be proven wrong in at least
  eighteen of them, using the journal alone.
- **SC-003**: Zero orders across all backtest, paper, and live history breach the risk envelope.
- **SC-004**: Re-running any archived run from its recorded data snapshot and configuration
  reproduces its decision journal exactly, with zero differences.
- **SC-005**: 100% of reported performance figures are net of modelled costs, and zero performance
  reports present a single metric in isolation.
- **SC-006**: 100% of orders for non-allow-listed symbols are rejected before transmission.
- **SC-007**: The operator can answer "why did the system act this way on this date?" in under one
  minute using only the journal.
- **SC-008**: The kill switch cancels all working orders and flattens all positions within ten
  seconds of being triggered.
- **SC-009**: Zero orders reach a live brokerage account; every order in this version is simulated
  and recorded as simulated.
- **SC-010**: Every trading principle used by the strategy has a lesson, and every closed trade
  has a review note — 100% coverage, no orphan principles.
- **SC-011**: After one month of use, the operator can correctly define and apply at least eight
  of the trading principles the system has used, assessed by self-test.
- **SC-012**: Zero occurrences of an order being transmitted without an accompanying explanation.

## Assumptions

- **Single operator, personal account.** The system is a personal trading and learning tool. It
  does not manage third-party funds, publish signals, or provide investment advice to others.
- **Explanations surface as a written journal plus real-time on-screen output.** A richer
  presentation layer is a later enhancement, not part of this feature.
- **Explanations are generated from the strategy's own rule structure**, not by an external
  narrator inspecting results after the fact — the reasoning must be the actual reasoning.
- **Historical gold data of adequate quality is obtainable** for the chosen instrument and
  horizon, covering enough history to include at least one significant drawdown and one strong
  trend.
- **The risk envelope defaults come from the project constitution**: 1.0% risk per trade, 3.0%
  daily loss halt, 2:1 maximum effective leverage, one open position at a time. Trading ETF shares
  in a cash account means effective leverage stays at 1:1, so the leverage cap is never the
  binding constraint here — it remains in force for any future instrument.
- **The daily loss limit is evaluated against losses realised within the session.** Unrealised
  drawdown on an open swing position is governed by that position's stop, not by the session halt,
  since a multi-day hold would otherwise trip the halt on ordinary fluctuation.
- **Position sizes are whole shares** unless the eventual broker supports fractional shares, so
  the risk-derived size rounds down and actual risk per trade sits at or below the limit.
- **The specific fund is chosen during planning**, based on the operator's broker and jurisdiction.
  This specification fixes only that it is a physically-backed gold ETF.
- **The market is closed most of the time.** Roughly seventeen and a half hours of every weekday
  plus the whole weekend fall outside the session, so gap risk is a structural feature of this
  instrument rather than an edge case, and stop levels are intentions rather than guarantees.
- **Broker and data provider selection is deferred to the planning phase**; this specification
  states what the system must do, not which services it uses.
- **The strategy's specific rules are not fixed by this specification.** This feature defines the
  decision, explanation, risk, and learning framework; which signals the strategy uses is a
  separate, replaceable concern — and the framework must remain valid when those rules change.
- **All internal timestamps are UTC**, with session logic stating its exchange timezone
  explicitly.
- **One trading account and one currency** for the first version; multi-account and
  multi-currency handling are out of scope.
- **Tax treatment, accounting exports, and regulatory reporting are out of scope.**

## Out of Scope for This Version

Deferred deliberately, each to be specified as its own feature when the prerequisites are met:

- **Live execution.** Once a strategy has passed backtest, walk-forward, and a paper period
  against written acceptance criteria, a separate feature will add gated live trading: enabling it
  must require deliberate human action, a confirmed risk envelope, a recorded passing result for
  every prior stage, and a re-read of the constitution. Live decisions must produce the same
  explanations and audit records as paper ones.
- **Broker-resident protective stops.** The constitution requires that stops rest with the broker
  rather than only in memory. Paper trading cannot exercise this, so it is unproven until the live
  feature exists and must be treated as an open risk at that point, not a solved one.
- **Short exposure**, whether by borrowing shares or through inverse products.
- **Instruments beyond the ETF allow-list** — futures, spot, options, or leveraged products —
  each of which would require an allow-list amendment plus covering tests.
- **Multiple accounts, multiple currencies, and portfolio-level allocation.**
- **A graphical dashboard.** Explanations surface as a written journal and on-screen output in
  this version.
