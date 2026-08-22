"""The individual checks the risk gate runs.

Each returns a `Rejection` or `None`. They are separate functions rather than
one long method so that each can be tested in isolation and so that a new limit
is an addition rather than an edit to a growing conditional.

Every rejection carries a sentence a person can read. A refused trade is a
teaching moment — "REJECTED: code 7" teaches nothing.
"""

from __future__ import annotations

from decimal import Decimal

from goldbot.domain.account import AccountState
from goldbot.domain.decision import Action, Decision
from goldbot.domain.envelope import RiskEnvelope
from goldbot.domain.instrument import AllowList
from goldbot.domain.verdict import Rejection


def check_halted(account: AccountState) -> Rejection | None:
    if not account.halted:
        return None
    return Rejection(
        kind="HALTED",
        statement=(
            "The session is halted and will not open new positions until an operator "
            f"resumes it deliberately. Reason on record: {account.halt_reason or 'unspecified'}."
        ),
        evidence={"halted": True, "reason": account.halt_reason},
    )


def check_is_entry(decision: Decision) -> Rejection | None:
    if decision.action is Action.ENTER and decision.plan is not None:
        return None
    return Rejection(
        kind="NOT_AN_ENTRY",
        statement=(
            f"Only an entry decision carrying a plan can be authorized; this one is "
            f"{decision.action.value} with "
            f"{'no plan' if decision.plan is None else 'a plan'}."
        ),
        evidence={"action": decision.action.value},
    )


def check_allow_list(decision: Decision, allow_list: AllowList) -> Rejection | None:
    if decision.symbol in allow_list:
        return None
    return Rejection(
        kind="ALLOW_LIST",
        statement=(
            f"{decision.symbol} is not on the gold allow-list {list(allow_list.symbols)}. "
            "This system trades gold and nothing else; related markets may inform a "
            "decision but may never be the thing it buys."
        ),
        evidence={"symbol": decision.symbol, "allowed": ", ".join(allow_list.symbols)},
    )


def check_per_trade_risk(decision: Decision, envelope: RiskEnvelope) -> Rejection | None:
    plan = decision.plan
    if plan is None:
        return None
    if plan.risk_pct <= envelope.max_risk_per_trade:
        return None
    return Rejection(
        kind="RISK_EXCEEDED",
        statement=(
            f"This entry would risk {plan.risk_pct:.2%} of equity against a limit of "
            f"{envelope.max_risk_per_trade:.2%}. Capital preservation comes before any "
            "individual setup, however good it looks."
        ),
        evidence={
            "requested_pct": plan.risk_pct,
            "limit_pct": envelope.max_risk_per_trade,
            "risk_amount": plan.risk_amount,
        },
    )


def check_daily_loss(account: AccountState, envelope: RiskEnvelope) -> Rejection | None:
    loss_fraction = account.daily_loss_fraction()
    if loss_fraction < envelope.max_daily_loss:
        return None
    return Rejection(
        kind="DAILY_LOSS_HALT",
        statement=(
            f"Realised losses today are {loss_fraction:.2%} of equity, at or beyond the "
            f"{envelope.max_daily_loss:.2%} daily limit. New entries stop here until the "
            "session is resumed deliberately — the limit exists precisely for the moment "
            "when trading feels most urgent."
        ),
        evidence={
            "realised_today": account.realised_today,
            "loss_fraction": loss_fraction,
            "limit": envelope.max_daily_loss,
        },
    )


def check_position_limit(account: AccountState, envelope: RiskEnvelope) -> Rejection | None:
    if account.open_count < envelope.max_concurrent_positions:
        return None
    return Rejection(
        kind="POSITION_LIMIT",
        statement=(
            f"{account.open_count} position(s) are already open and the limit is "
            f"{envelope.max_concurrent_positions}. Concentration is the risk this limit "
            "controls, and it is not negotiable per setup."
        ),
        evidence={"open": account.open_count, "limit": envelope.max_concurrent_positions},
    )


def check_cash(decision: Decision, account: AccountState) -> Rejection | None:
    plan = decision.plan
    if plan is None:
        return None
    cost: Decimal = plan.intended_entry * plan.shares
    if cost <= account.cash:
        return None
    return Rejection(
        kind="INSUFFICIENT_CASH",
        statement=(
            f"Buying {plan.shares} shares at {plan.intended_entry:.2f} costs {cost:.2f}, "
            f"but only {account.cash:.2f} is available. This is a cash account: there is "
            "no borrowing to fall back on."
        ),
        evidence={"cost": cost, "cash": account.cash, "shares": plan.shares},
    )


def check_leverage(decision: Decision, account: AccountState, envelope: RiskEnvelope) -> Rejection | None:
    """Never binding in a cash account, kept because a future instrument might reach it."""
    plan = decision.plan
    if plan is None or account.equity <= 0:
        return None
    exposure = plan.intended_entry * plan.shares
    leverage = exposure / account.equity
    if leverage <= envelope.max_leverage:
        return None
    return Rejection(
        kind="LEVERAGE",
        statement=(
            f"Exposure of {exposure:.2f} against equity of {account.equity:.2f} is "
            f"{leverage:.2f}x, beyond the {envelope.max_leverage:.2f}x limit."
        ),
        evidence={"exposure": exposure, "equity": account.equity, "leverage": leverage},
    )
