"""Promotion between stages.

    BACKTEST -> WALK_FORWARD -> PAPER -> (nothing)

`LIVE` is deliberately not defined. FR-024 says this version has no live path,
and the cleanest way to say that in code is for the state to be unrepresentable
rather than reachable-but-blocked. Adding it is a separate, specified feature.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

from goldbot.domain.errors import GuardViolation


class Stage(str, Enum):
    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    PAPER = "PAPER"


#: What must be passed before each stage can be entered.
PREREQUISITES: dict[Stage, tuple[Stage, ...]] = {
    Stage.BACKTEST: (),
    Stage.WALK_FORWARD: (Stage.BACKTEST,),
    Stage.PAPER: (Stage.BACKTEST, Stage.WALK_FORWARD),
}


@dataclass(frozen=True, slots=True)
class StagePass:
    """Evidence that a stage's acceptance criteria were met."""

    stage: Stage
    run_id: str
    at: str
    expectancy_r: str
    trade_count: int
    note: str = ""


@dataclass
class PromotionState:
    """Which stages a strategy has cleared, and what proved it."""

    config_version: str
    passes: dict[str, StagePass] = field(default_factory=dict)

    def has_passed(self, stage: Stage) -> bool:
        return stage.value in self.passes

    def missing_for(self, stage: Stage) -> list[Stage]:
        return [s for s in PREREQUISITES[stage] if not self.has_passed(s)]

    def require(self, stage: Stage) -> None:
        """Refuse to enter a stage whose prerequisites are unmet (FR-023)."""
        missing = self.missing_for(stage)
        if missing:
            names = ", ".join(s.value for s in missing)
            raise GuardViolation(
                f"cannot start {stage.value}: {names} has not recorded a passing result. "
                "Promotion runs backtest -> walk-forward -> paper, in that order, against "
                "criteria written down before the run. Skipping a stage is how a strategy "
                "reaches real conditions untested."
            )

    def record(
        self,
        stage: Stage,
        *,
        run_id: str,
        at: datetime,
        expectancy_r: str,
        trade_count: int,
        note: str = "",
    ) -> None:
        self.passes[stage.value] = StagePass(
            stage=stage,
            run_id=run_id,
            at=at.isoformat(),
            expectancy_r=expectancy_r,
            trade_count=trade_count,
            note=note,
        )

    # -- persistence ------------------------------------------------------

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "config_version": self.config_version,
            "passes": {k: asdict(v) | {"stage": v.stage.value} for k, v in self.passes.items()},
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path, config_version: str) -> PromotionState:
        if not path.exists():
            return cls(config_version=config_version)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("config_version") != config_version:
            # A changed config is a different strategy. Its predecessor's
            # results do not transfer, which is the point of versioning them.
            return cls(config_version=config_version)
        passes = {
            key: StagePass(
                stage=Stage(value["stage"]),
                run_id=value["run_id"],
                at=value["at"],
                expectancy_r=value["expectancy_r"],
                trade_count=value["trade_count"],
                note=value.get("note", ""),
            )
            for key, value in payload.get("passes", {}).items()
        }
        return cls(config_version=config_version, passes=passes)
