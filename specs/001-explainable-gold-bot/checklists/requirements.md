# Specification Quality Checklist: Explainable Gold Trading Bot

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-08-21
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`

### Iteration 1 — 2026-08-21

Two items failed, both traceable to three deliberate `[NEEDS CLARIFICATION]` markers in FR-033,
FR-034, and FR-035: gold instrument form, decision cadence, and version 1 scope. None were
defaulted, because each materially changes the size and risk of the build.

Two content-quality fixes applied in this iteration:

- Replaced "terminal output" with "on-screen output" in Assumptions (delivery-mechanism detail).
- Replaced "configuration hash" with "configuration version" in the Run Artifact entity.

### Iteration 2 — 2026-08-21 — all items pass

Operator answered all three questions. Decisions recorded:

- **Instrument**: shares in a physically-backed gold ETF, held in a cash account (FR-033).
- **Cadence**: completed daily bars by default, 4-hour bars configurable (FR-034).
- **Version 1 scope**: User Stories 1 through 3, stopping at paper trading (FR-035).

Consequential changes propagated beyond the three markers, since each answer invalidated
assumptions elsewhere in the spec:

| Change | Driver |
|---|---|
| FR-021 cost model: overnight financing replaced by expense-ratio drag | Cash-account ETF shares accrue no swap |
| FR-024 hardened: no live order path may exist at all, not merely disabled by default | Paper-only scope makes absence testable, which "disabled" is not |
| FR-036 added: signals and execution levels must both come from the ETF's own price series | Spot gold trades nearly continuously while the ETF does not; mixing the two would invalidate every backtest |
| FR-037 added: long or flat only | Shorting shares requires margin, excluded by the cash-account choice |
| FR-038 added: decisions on closed bars execute at the next open, recording the price difference | Daily-bar decisions land while the exchange is shut |
| User Story 4 moved to a new "Out of Scope for This Version" section | Paper-only scope |
| SC-009 rewritten to assert zero live orders | Follows FR-024 |
| Four edge cases added or rewritten: overnight/weekend gaps, exchange halts, ETF dislocation from spot, whole-share rounding | All specific to an exchange-listed, cash-settled share |
| Assumptions added: daily-loss-limit basis, whole-share sizing, 1:1 effective leverage, structural gap risk | Consequences of the instrument and cadence |

Two points carried forward as known risks rather than resolved items:

- **Broker-resident stops are unprovable in this version.** The constitution requires stops to
  rest with the broker; paper trading cannot exercise that. Recorded in Out of Scope as an open
  risk to confront when the live feature is specified, not as a solved problem.
- **Stops are intentions, not guarantees.** With the market closed roughly seventeen and a half
  hours per weekday plus weekends, a swing position's realised loss can exceed its planned risk
  through a gap. Captured in Edge Cases and Assumptions so that expectancy is judged including
  those overruns.

Final counts: 38 functional requirements, 12 success criteria, 3 prioritized user stories, 15 edge
cases. No blocking issues. Ready for `/speckit-plan`.
