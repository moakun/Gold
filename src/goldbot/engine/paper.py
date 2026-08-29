"""Paper trading.

**Paper is a replay, not a second engine.** Each session step re-runs the whole
history through the same `DecisionLoop` a backtest uses, with a sticky halt,
and reports the newest decision. State — cash, position, whether the halt is
set — is derived rather than stored.

That choice is deliberate. Keeping a separate live state machine in sync with
the backtest engine is the classic way a strategy ends up behaving one way in
simulation and another in practice. Deriving state by replay makes divergence
impossible: there is only one implementation of "what would this strategy do".

The cost is recomputing a few thousand bars per invocation, which takes under a
second and buys a guarantee.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from goldbot.config import Config
from goldbot.domain.bar import Bar
from goldbot.domain.decision import Action, Decision
from goldbot.domain.errors import HaltRequired
from goldbot.domain.money import ZERO
from goldbot.engine.calendar import ExchangeSessions
from goldbot.engine.loop import DecisionLoop, RunResult
from goldbot.execution.simulated import SimulatedBroker
from goldbot.journal.store import AuditStore
from goldbot.risk.gate import RiskGate

#: How many sessions of silence before the feed is considered stale. Two allows
#: for a single missed fetch; three days of nothing means something is wrong.
STALE_AFTER_SESSIONS = 2


@dataclass(frozen=True, slots=True)
class PaperState:
    """What an operator wants to see after a session step."""

    latest_decision: Decision
    open_position: bool
    position_shares: int
    position_stop: Decimal
    equity: Decimal
    halted: bool
    halt_reason: str
    trades: int
    next_session_open: datetime | None
    stale: bool
    stale_reason: str = ""

    def to_json(self) -> str:
        return json.dumps(
            {
                "as_of": self.latest_decision.as_of.isoformat(),
                "action": self.latest_decision.action.value,
                "open_position": self.open_position,
                "shares": self.position_shares,
                "stop": str(self.position_stop),
                "equity": str(self.equity),
                "halted": self.halted,
                "halt_reason": self.halt_reason,
                "trades": self.trades,
                "next_session_open": (
                    self.next_session_open.isoformat() if self.next_session_open else None
                ),
                "stale": self.stale,
                "execution": "simulated",
            },
            indent=2,
            sort_keys=True,
        )


def resume_marker_path(root: Path) -> Path:
    return root / "paper" / "resume.json"


def read_resume_date(root: Path) -> date | None:
    path = resume_marker_path(root)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    value = payload.get("cleared_after")
    return date.fromisoformat(value) if value else None


def write_resume_date(root: Path, cleared_after: date, note: str = "") -> None:
    path = resume_marker_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"cleared_after": cleared_after.isoformat(), "note": note},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def check_staleness(
    bars: tuple[Bar, ...], *, now: datetime, sessions: ExchangeSessions
) -> tuple[bool, str]:
    """Has the data stopped arriving?

    Stale data with a position open is the scenario SAFE mode exists for: the
    system must stop opening anything new while leaving the existing stop in
    force, rather than deciding on prices that may no longer be true.
    """
    if not bars:
        return True, "no bars at all"

    last = bars[-1].end.date()
    expected = [
        d
        for d in sessions.sessions_between(last + timedelta(days=1), now.date())
        if d < now.date()
    ]
    if len(expected) > STALE_AFTER_SESSIONS:
        return True, (
            f"the newest bar is {last.isoformat()} and {len(expected)} session(s) have "
            "closed since. Decisions will not be made on prices this old."
        )
    return False, ""


def run_session(
    *,
    config: Config,
    bars: tuple[Bar, ...],
    run_id: str,
    store: AuditStore,
    kill_latch: Path | None,
    runs_root: Path,
    now: datetime | None = None,
    safe_mode: bool = False,
) -> tuple[RunResult, PaperState]:
    """Replay everything, then report the newest decision."""
    moment = now or datetime.now(UTC)
    sessions = ExchangeSessions(config.instrument.calendar)

    stale, stale_reason = check_staleness(bars, now=moment, sessions=sessions)
    if stale and not safe_mode:
        raise HaltRequired(
            f"SAFE mode: {stale_reason} No new entries will be opened. Any existing stop "
            "remains in force."
        )

    gate = RiskGate(
        allow_list=config.allow_list,
        envelope=config.envelope,
        kill_latch=kill_latch,
    )
    loop = DecisionLoop(
        config=config,
        bars=bars,
        gate=gate,
        broker=SimulatedBroker(config.instrument, run_id=run_id),
        run_id=run_id,
        store=store,
        halt_resumes_next_session=False,
        halt_cleared_after=read_resume_date(runs_root),
    )
    result = loop.run()

    for rejection in gate.rejections:
        store.record_violation(run_id, moment, rejection)

    latest = result.decisions[-1]
    open_position = latest.action in (Action.ENTER,) or _still_open(result)
    shares = latest.plan.shares if latest.plan else 0
    stop = latest.plan.stop if latest.plan else ZERO

    state = PaperState(
        latest_decision=latest,
        open_position=open_position,
        position_shares=shares,
        position_stop=stop,
        equity=result.ending_equity,
        halted=bool(result.halts),
        halt_reason=result.halts[-1][2] if result.halts else "",
        trades=len(result.trades),
        next_session_open=sessions.next_session_open(moment),
        stale=stale,
        stale_reason=stale_reason,
    )
    return result, state


def _still_open(result: RunResult) -> bool:
    """Whether the replay ended holding something.

    The loop closes any open position at the end of data with END_OF_DATA, so
    a paper session is flat by the time it returns. This reports whether the
    last thing that happened was that forced close rather than a real exit.
    """
    from goldbot.domain.position import ExitReason

    return bool(result.trades) and result.trades[-1].exit_reason is ExitReason.END_OF_DATA
