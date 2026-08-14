<!--
Sync Impact Report
- Version change: (unversioned template) -> 1.0.0
- Bump rationale: Initial ratification. All template placeholders replaced with concrete,
  project-specific governance for a gold-only algorithmic trading system with an explicit
  teaching mandate.
- Principles defined (template slot -> ratified name):
  - Principle 1 slot -> I. Capital Preservation First (NON-NEGOTIABLE)
  - Principle 2 slot -> II. Gold-Only Scope
  - Principle 3 slot -> III. Every Decision Is Explained (Teaching Mandate)
  - Principle 4 slot -> IV. Simulate Before Risking Money (NON-NEGOTIABLE)
  - Principle 5 slot -> V. Reproducible and Auditable by Default
- Added sections:
  - Section 2 slot -> Risk, Safety, and Operating Constraints
  - Section 3 slot -> Development Workflow and Quality Gates
  - Governance rules populated
- Removed sections: none
- Deferred / follow-up items:
  - The default risk envelope (1% per trade, 3% daily stop, 2:1 max leverage, 1 open position)
    is a provisional default inferred for a single-operator learning account. It is binding until
    amended through the Governance process.
-->
# Gold Trading Bot Constitution

## Core Principles

### I. Capital Preservation First (NON-NEGOTIABLE)

- Every order MUST carry a predetermined stop-loss level and a position size derived from that
  stop before transmission. The risk layer MUST reject any order missing either.
- Risk on a single trade MUST NOT exceed `max_risk_per_trade` (default: 1.0% of account equity).
- When cumulative session loss reaches `max_daily_loss` (default: 3.0% of starting equity), the
  system MUST block new entries and MUST require explicit human re-enable to resume.
- Widening a stop after entry, removing a stop, and averaging down into a losing position are
  FORBIDDEN. The codebase MUST NOT expose an API capable of performing them.

Rationale: A system that survives its drawdowns can compound; one that does not is unrecoverable
regardless of how good its edge was. Encoding these limits in software removes them from the reach
of in-the-moment emotion, which is where discretionary traders most reliably fail.

### II. Gold-Only Scope

- The tradable universe is restricted to gold instruments: spot XAU/USD, gold futures (GC/MGC),
  and gold ETFs named in an explicit instrument allow-list.
- The order router MUST fail closed. Any symbol absent from the allow-list is rejected and the
  rejection is logged. Extending the allow-list requires a code change plus a covering test.
- Correlated markets (DXY, real yields, silver, gold miners, VIX) MAY be consumed as input data
  but MUST NOT be traded.

Rationale: One instrument understood deeply beats many traded shallowly. Gold's drivers — real
yields, the dollar, central-bank demand, and risk sentiment — form a bounded curriculum a learner
can actually master, and a bounded universe keeps the operational risk surface small.

### III. Every Decision Is Explained (Teaching Mandate)

- Every signal, entry, exit, sizing decision, and deliberately skipped setup MUST emit a
  plain-language explanation that names the trading principle being applied.
- Each explanation MUST state the concrete evidence that triggered it, the invalidation level
  (where the idea is proven wrong), and the reward-to-risk ratio being accepted.
- A model or indicator that cannot produce a human-readable attribution MUST NOT be granted
  order-placing authority.
- Every closed trade MUST produce a review note: what was expected, what happened, and which
  principle the outcome confirms or contradicts.

Rationale: This project has two deliverables — trades and understanding. A black box that prints a
P&L curve teaches nothing, and an operator who cannot explain why the system acted cannot
supervise it, debug it, or decide when to switch it off.

### IV. Simulate Before Risking Money (NON-NEGOTIABLE)

- Promotion gates run strictly in order: backtest -> walk-forward on unseen data -> paper trading
  -> live. A strategy advances only by meeting acceptance criteria written down *before* the run.
- Backtests MUST be deterministic and reproducible from a pinned data snapshot plus a config hash.
- Backtests MUST model spread, commission, slippage, and overnight swap/carry. Frictionless
  results are invalid and MUST NOT be reported as performance.
- Look-ahead bias defenses are mandatory: decisions on closed bars only, no future data in feature
  construction, and no parameter chosen using the evaluation window.
- Live trading MUST default to disabled and MUST be enabled only by explicit human action, never
  by the bot and never by an automated agent.

Rationale: This is test-first discipline applied to capital. A backtest is a unit test, paper
trading is staging, and live money is production — promoting straight to production is how
accounts are lost to bugs that a simulation would have caught for free.

### V. Reproducible and Auditable by Default

- Every signal, order, fill, rejection, config version, and data snapshot MUST be persisted to an
  append-only log with UTC timestamps.
- Performance MUST be reported net of all costs and MUST present expectancy, win rate, average R
  multiple, maximum drawdown, and trade count together. No single metric may be quoted alone.
- Secrets (API keys, account identifiers, tokens) MUST be loaded from environment variables or a
  secret store, and MUST NEVER be committed to the repository or written to logs.
- Any claim made about strategy performance MUST be traceable to a stored run artifact.

Rationale: You cannot learn from a history you cannot reconstruct, and you cannot trust a number
you cannot re-derive. Auditability is the precondition for both improvement and safety.

## Risk, Safety, and Operating Constraints

- Default risk envelope, binding until amended: 1.0% risk per trade, 3.0% daily loss stop, 2:1
  maximum effective leverage, and at most 1 open gold position at a time.
- A kill switch MUST exist: a single command that cancels all working orders, flattens all
  positions, and blocks new entries until manually cleared.
- Stops MUST rest at the broker, not only in local memory, so that a crashed or disconnected bot
  still leaves protected positions.
- On stale market data, broker disconnection, or an unhandled exception in the decision path, the
  system MUST enter SAFE mode: no new entries, existing broker-side stops left in place, operator
  alerted.
- Scheduled high-impact events (FOMC, CPI, NFP) MUST be handled by an explicit, configured policy
  — trade, reduce size, or stand aside — never left to chance.
- The system is a single-operator personal trading and learning tool. It does not provide
  investment advice, does not manage third-party funds, and MUST NOT be distributed as a signal
  service or advisory product without amending this constitution.
- All internal timestamps are UTC. Any session or trading-hours logic MUST state its exchange
  timezone explicitly rather than relying on machine local time.

## Development Workflow and Quality Gates

- Features follow the Spec Kit flow: `/speckit-specify` -> `/speckit-plan` -> `/speckit-tasks` ->
  `/speckit-implement`. Trading logic is not written ad hoc.
- Risk-layer code (position sizing, stop enforcement, kill switch, instrument allow-list) requires
  unit tests covering the rejection paths, and those tests MUST fail before the guard is
  implemented.
- Any change to strategy logic requires re-running the reproducible backtest and attaching the
  before/after metric diff to the change.
- A decision path shipped without its explanation text is an incomplete feature and MUST NOT be
  merged (see Principle III).
- Each trading concept implemented in code MUST be paired with a short lesson note in the docs
  explaining the concept, when it works, and when it fails.
- CI and test environments MUST NOT hold live-trading credentials.

## Governance

This constitution supersedes ad-hoc practice and informal preference. Where a request conflicts
with a principle here, the principle wins until the constitution is amended.

Amendment procedure: propose the change with its rationale and its risk implication, record it in
the Sync Impact Report at the top of this file, apply the version bump, and update the amendment
date. Risk-envelope numbers and the instrument allow-list are amendable only through this process,
never by inline override at runtime.

Versioning policy follows semantic versioning:

- MAJOR: a principle is removed or redefined in a backward-incompatible way.
- MINOR: a principle or section is added, or guidance is materially expanded.
- PATCH: clarifications, wording, and non-semantic refinements.

Compliance review: every plan and implementation review MUST verify that the change respects the
five core principles, and complexity that violates the spirit of a principle MUST be justified in
writing or removed. Before any transition from paper to live trading, this constitution MUST be
re-read in full and the risk envelope reconfirmed by the operator.

**Version**: 1.0.0 | **Ratified**: 2026-08-14 | **Last Amended**: 2026-08-14
