"""The atom of explanation.

Every rule returns exactly one `Verdict`, whether or not its condition was met.
A rule that cannot produce one cannot participate in a decision, which is how
FR-007 keeps unexplainable signal sources away from the order path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

EvidenceValue = Decimal | str | int | bool
Evidence = Mapping[str, EvidenceValue]


@dataclass(frozen=True)
class Verdict:
    """One rule's judgment, carrying the reasoning that produced it.

    `evidence` holds the actual values compared, not a summary of them. The
    difference matters when you are trying to learn: "trend is up" teaches
    nothing, "close 312.44 is above its 200-day average 298.10" teaches the
    shape of the rule.
    """

    rule_id: str
    principle: str
    passed: bool
    evidence: Evidence
    statement: str

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("a verdict needs a rule_id")
        if not self.principle.strip():
            raise ValueError(f"{self.rule_id}: a verdict must name the principle it applies")
        if not self.statement.strip():
            raise ValueError(
                f"{self.rule_id}: a verdict must state its reasoning in words; "
                "an unexplainable rule cannot reach the order path"
            )
        if not self.evidence:
            raise ValueError(
                f"{self.rule_id}: a verdict must carry the evidence it judged, "
                "so the statement can be checked against the numbers"
            )
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def __str__(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        return f"[{mark}] {self.statement}"


@dataclass(frozen=True)
class Rejection:
    """A refusal by the risk gate, carrying a verdict-quality explanation.

    A refused trade is a teaching moment rather than an error line, so a
    rejection has to explain itself as well as a rule does.
    """

    kind: str
    statement: str
    evidence: Evidence = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("a rejection needs a kind")
        if not self.statement.strip():
            raise ValueError(f"{self.kind}: a rejection must explain itself in words")
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    def __str__(self) -> str:
        return f"[REJECTED:{self.kind}] {self.statement}"
