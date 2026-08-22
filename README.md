# Gold Trading Bot

A gold-only trading bot that explains every decision it makes — and, in doing so, teaches the trading principles behind them.

The project has two deliverables of equal weight: a strategy that trades gold under strict risk
rules, and an operator who understands why it does what it does. A black box that prints a profit
curve would fail half the brief.

> **Status: specification phase.** There is no runnable code in this repository yet. What exists
> is the governing constitution and a validated specification for the first feature. See
> [Where this stands](#where-this-stands).

## Why it works this way

Three rules shape every decision in the design:

**Every decision is explained.** Not just entries and exits — the bot also explains the bars where
it deliberately did nothing, naming the condition that was missing. Each explanation states the
evidence, the trading principle applied, where the idea would be proven wrong, and the
reward-to-risk being accepted. Anything that cannot explain itself is not allowed to place orders.

**Gold only.** The tradable universe is an explicit allow-list. Related markets — the dollar, real
yields, silver, miners — can inform a decision but can never be traded. One instrument understood
deeply beats many traded shallowly, and a narrow universe keeps the risk surface small.

**Nothing reaches real money untested.** The promotion path is backtest → walk-forward → paper →
live, in that order, against criteria written down before each run. The first version stops at
paper trading and contains no code path capable of reaching a live brokerage account.

## Scope of version 1

| Decision | Value |
|---|---|
| Instrument | Shares in a physically-backed gold ETF, cash account |
| Direction | Long or flat only — no shorting, no leveraged or inverse products |
| Cadence | Completed daily bars by default; 4-hour bars configurable |
| Furthest stage | Paper trading. No live execution path exists in this version |
| Risk per trade | 1.0% of account equity |
| Daily loss halt | 3.0% of starting equity, requiring manual resume |
| Concurrent positions | One |

Two consequences of the instrument choice are worth stating plainly, because they are structural
rather than edge cases:

- **Stops are intentions, not guarantees.** The exchange is closed roughly seventeen and a half
  hours every weekday and all weekend. A swing position routinely spans that gap and can reopen
  beyond its stop, losing more than the planned 1%. Performance must be judged including those
  overruns.
- **Signals and execution come from the same price series.** Spot gold trades nearly continuously;
  the ETF does not. Generating signals from spot data and executing on ETF shares would produce a
  backtest that looks excellent and cannot be traded.

## The learning layer

Explanations alone teach tactically but leave fragments. Three mechanisms turn them into
cumulative understanding:

- Every principle named in a decision links to a **lesson** — what the concept is, when it works,
  when it fails, and how it behaves in gold specifically.
- Every closed trade produces a **review note** contrasting what was expected at entry with what
  actually happened, and whether the outcome supports or contradicts the principle applied.
- Losses taken correctly according to the rules are **distinguished from losses caused by rule
  violations or errors** — a critical distinction that most trading journals collapse.

## Where this stands

This project is built with [Spec Kit](https://github.com/github/spec-kit), which sequences work
through explicit phases rather than jumping to code.

- [x] **Constitution** — five binding principles ratified at v1.0.0
- [x] **Specify** — feature 001 specified and validated, 15/15 quality checks passing
- [x] **Plan** — Python 3.11 + uv, bespoke event-driven engine, no brokerage SDK at all
- [x] **Tasks** — 107 tasks across 6 phases, organised by user story
- [ ] **Implement** — build

The next step is `/speckit-implement`. The MVP is User Story 1: an explained backtest, which needs
Phases 1 through 3 (tasks T001–T063).

## Repository layout

```
.specify/
  memory/constitution.md      Binding project principles — read this first
  templates/                  Spec Kit document scaffolds
  scripts/                    Spec Kit automation
specs/
  001-explainable-gold-bot/
    spec.md                   Feature specification: 38 requirements, 3 user stories
    plan.md                   Architecture, stack, and constitution gate checks
    research.md               12 technical decisions and what was rejected
    data-model.md             Types, invariants, and state machines
    contracts/                CLI surface, internal interfaces, durable records
    quickstart.md             7 validation scenarios mapped to requirements
    tasks.md                  107 implementation tasks, dependency-ordered
    checklists/requirements.md  Quality validation record and decision log
.claude/skills/               Spec Kit slash commands
```

## Key documents

- **[Constitution](.specify/memory/constitution.md)** — the five principles, the risk envelope,
  and the amendment process. Everything else defers to this document.
- **[Feature 001 specification](specs/001-explainable-gold-bot/spec.md)** — explained backtest,
  explained paper trading, and the principles curriculum.
- **[Requirements checklist](specs/001-explainable-gold-bot/checklists/requirements.md)** — the
  validation record, including why each scope decision was made.

## Scope and disclaimer

This is a single-operator personal trading and learning tool. It does not provide investment
advice, does not manage third-party funds, and is not a signal service. Nothing produced by this
system is a recommendation to buy or sell anything.

Trading involves risk of loss. The risk controls described here are engineering safeguards against
predictable mistakes — they are not protection against losing money, and no backtest result
predicts future returns.
