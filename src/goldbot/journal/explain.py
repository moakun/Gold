"""Turning verdicts into prose.

The explainer sees a `Decision` and nothing else. It cannot see the outcome,
later bars, or the equity curve — so it cannot write narration, only report the
reasoning that actually ran. That restriction is the difference between a
system that explains itself and one that rationalises afterwards.
"""

from __future__ import annotations

from goldbot.domain.decision import Action, Decision, EntryPlan
from goldbot.domain.verdict import Verdict


def _plan_sentence(plan: EntryPlan) -> str:
    reward = plan.reward_risk
    target_part = (
        f" targeting {plan.target:.2f} for {reward:.2f}:1 reward-to-risk"
        if plan.target is not None and reward is not None
        else " with no fixed target; the exit rule decides when to leave"
    )
    return (
        f"Buying {plan.shares} shares around {plan.intended_entry:.2f}, wrong below "
        f"{plan.stop:.2f}. That risks {plan.risk_amount:.2f}, {plan.risk_pct:.2%} of equity"
        f"{target_part}."
    )


def render_verdicts(verdicts: tuple[Verdict, ...]) -> str:
    return "\n".join(f"  - {v}" for v in verdicts)


def explain(decision: Decision) -> str:
    """The plain-language explanation stored with every decision.

    Written for someone who does not know the strategy's internals. Bare
    indicator values without stated meaning would fail FR-008.
    """
    passed = decision.passed_verdicts()
    failed = decision.failed_verdicts()

    if decision.action is Action.ENTER:
        assert decision.plan is not None
        lead = "Entering a long position. Every condition held:"
        body = render_verdicts(decision.verdicts)
        return f"{lead}\n{body}\n\n{_plan_sentence(decision.plan)}"

    if decision.action is Action.SKIP:
        assert decision.blocking_verdict is not None
        blocker = decision.blocking_verdict
        lead = f"No trade. {blocker.statement}"
        if passed:
            satisfied = ", ".join(v.rule_id for v in passed)
            lead += (
                f"\n\nThe rest of the setup was in place ({satisfied}), so this was a near "
                "miss rather than an absent signal:"
            )
        else:
            lead += "\n\nNothing else was in place either:"
        return f"{lead}\n{render_verdicts(decision.verdicts)}"

    if decision.action is Action.EXIT:
        reason = failed[0] if failed else decision.verdicts[0]
        return (
            f"Closing the position. {reason.statement}\n\n"
            f"{render_verdicts(decision.verdicts)}"
        )

    # HOLD
    if decision.verdicts:
        return (
            "Holding. The reason for being in this trade still stands:\n"
            f"{render_verdicts(decision.verdicts)}"
        )
    return "Holding."


def one_line(decision: Decision) -> str:
    """A single line for a scrolling session view."""
    stamp = decision.as_of.date().isoformat()
    if decision.action is Action.ENTER and decision.plan is not None:
        return (
            f"{stamp}  ENTER  {decision.plan.shares} shares, stop {decision.plan.stop:.2f}, "
            f"risking {decision.plan.risk_pct:.2%}"
        )
    if decision.action is Action.SKIP and decision.blocking_verdict is not None:
        return f"{stamp}  SKIP   {decision.blocking_verdict.rule_id}"
    if decision.action is Action.EXIT:
        return f"{stamp}  EXIT"
    return f"{stamp}  HOLD"
