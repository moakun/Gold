"""The only door to the broker.

Every order in this system passes through `RiskGate.authorize`. It is the sole
holder of `_mint_authorization`, and the simulated broker accepts nothing but
an `Authorization`, so there is no way to place a trade that skipped these
checks.

That property is what makes Principle I structural. The alternative — checking
risk at each call site and trusting everyone to remember — is how accounts get
blown up by a code path somebody added on a Friday.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from goldbot.domain.account import AccountState
from goldbot.domain.decision import Decision
from goldbot.domain.envelope import RiskEnvelope
from goldbot.domain.instrument import AllowList
from goldbot.domain.order import Authorization, Side, _mint_authorization
from goldbot.domain.verdict import Rejection
from goldbot.risk.limits import (
    check_allow_list,
    check_cash,
    check_daily_loss,
    check_halted,
    check_is_entry,
    check_leverage,
    check_per_trade_risk,
    check_position_limit,
)


class RiskGate:
    """Approves or refuses entries, and records why either way."""

    def __init__(
        self,
        *,
        allow_list: AllowList,
        envelope: RiskEnvelope,
        kill_latch: Path | None = None,
    ) -> None:
        self.allow_list = allow_list
        self.envelope = envelope
        self.kill_latch = kill_latch
        #: Every call, granted or refused. An empty rejection log across a long
        #: run means the guards were never exercised, which is worth knowing.
        self.rejections: list[Rejection] = []
        self.grants: int = 0

    def _kill_switch_engaged(self) -> Rejection | None:
        if self.kill_latch is None or not self.kill_latch.exists():
            return None
        return Rejection(
            kind="KILL_SWITCH",
            statement=(
                "The kill switch is engaged. No new position will be opened until it is "
                "cleared explicitly, which is the only way to release it."
            ),
            evidence={"latch": str(self.kill_latch)},
        )

    def authorize(
        self, decision: Decision, account: AccountState, *, now: datetime
    ) -> Authorization | Rejection:
        """Grant permission to trade, or refuse with an explanation.

        Checks run cheapest-and-most-absolute first: a kill switch outranks a
        halt, which outranks the allow-list, which outranks anything about
        sizing. The order matters because the first refusal is the one the
        operator reads.
        """
        checks = (
            self._kill_switch_engaged(),
            check_halted(account),
            check_is_entry(decision),
            check_allow_list(decision, self.allow_list),
            check_per_trade_risk(decision, self.envelope),
            check_daily_loss(account, self.envelope),
            check_position_limit(account, self.envelope),
            check_leverage(decision, account, self.envelope),
            check_cash(decision, account),
        )
        for rejection in checks:
            if rejection is not None:
                self.rejections.append(rejection)
                return rejection

        assert decision.plan is not None  # guaranteed by check_is_entry
        self.grants += 1
        return _mint_authorization(
            decision_id=decision.id,
            symbol=decision.symbol,
            side=Side.BUY,
            plan=decision.plan,
            issued_at=now,
            envelope_version=self.envelope.version,
        )
