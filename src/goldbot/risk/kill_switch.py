"""The kill switch.

One command that stops everything, and a latch that keeps it stopped. The latch
is a file rather than a variable so that it survives the process dying —
"stopped" should not quietly become "running" because something crashed and
was restarted.

Releasing it requires an explicit second command. Nothing clears it on a timer,
at midnight, or on restart, because every one of those would eventually release
it at the worst moment.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class KillResult:
    """What the kill switch actually did, and how long it took."""

    orders_cancelled: int
    positions_flattened: int
    elapsed_seconds: float
    latch_path: Path
    already_engaged: bool = False


class KillSwitch:
    """Cancel, flatten, latch."""

    def __init__(self, latch_path: Path) -> None:
        self.latch_path = latch_path

    @property
    def engaged(self) -> bool:
        return self.latch_path.exists()

    def reason(self) -> str:
        if not self.engaged:
            return ""
        return self.latch_path.read_text(encoding="utf-8").strip()

    def engage(
        self,
        *,
        at: datetime,
        cancel: int = 0,
        flatten: int = 0,
        note: str = "",
    ) -> KillResult:
        """Set the latch. Idempotent — safe to run when nothing is open.

        The caller does the cancelling and flattening (it owns the broker) and
        reports the counts; this owns the latch.
        """
        started = time.monotonic()
        already = self.engaged
        self.latch_path.parent.mkdir(parents=True, exist_ok=True)
        if not already:
            body = f"engaged at {at.isoformat()}"
            if note:
                body += f"\n{note}"
            self.latch_path.write_text(body + "\n", encoding="utf-8")
        return KillResult(
            orders_cancelled=cancel,
            positions_flattened=flatten,
            elapsed_seconds=time.monotonic() - started,
            latch_path=self.latch_path,
            already_engaged=already,
        )

    def clear(self) -> bool:
        """Release the latch. The only way it is ever released."""
        if not self.engaged:
            return False
        self.latch_path.unlink()
        return True
