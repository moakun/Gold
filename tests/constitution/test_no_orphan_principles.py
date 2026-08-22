"""Principle III: no rule ships without the lesson that explains it.

The constitution's development workflow requires each trading concept in code
to be paired with a lesson. This test is that requirement, executable: add a
rule with a new principle and forget the lesson, and the suite fails.

It also runs the check in the other direction. An orphan lesson — a concept
documented but no longer used by any rule — is a smaller problem, but it is
still the documentation drifting away from the code.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from goldbot.strategy.rules import ALL_PRINCIPLES, ALL_RULE_CLASSES

pytestmark = pytest.mark.constitution

CONTENT = Path(__file__).resolve().parents[2] / "src" / "goldbot" / "lessons" / "content"
REQUIRED_SECTIONS = ("## What it is", "## When it works", "## When it fails", "## In gold")


def lesson_ids() -> set[str]:
    return {p.stem for p in CONTENT.glob("*.md")}


def test_every_rule_declares_a_principle() -> None:
    for cls in ALL_RULE_CLASSES:
        assert getattr(cls, "principle", "").strip(), f"{cls.__name__} declares no principle"
        assert getattr(cls, "rule_id", "").strip(), f"{cls.__name__} declares no rule_id"


def test_every_principle_has_a_lesson() -> None:
    missing = sorted(set(ALL_PRINCIPLES) - lesson_ids())
    assert not missing, (
        f"these principles are used by rules but have no lesson: {missing}. "
        "A rule that trades a concept without teaching it fails half this project's purpose."
    )


def test_no_lesson_is_orphaned() -> None:
    orphans = sorted(lesson_ids() - set(ALL_PRINCIPLES))
    assert not orphans, f"these lessons describe concepts no rule uses any more: {orphans}"


def test_rule_ids_are_unique() -> None:
    ids = [cls.rule_id for cls in ALL_RULE_CLASSES]
    assert len(ids) == len(set(ids)), f"duplicate rule_id among {ids}"


@pytest.mark.parametrize("principle", ALL_PRINCIPLES)
def test_each_lesson_covers_the_four_required_sections(principle: str) -> None:
    """A lesson that omits "when it fails" is marketing, not teaching."""
    text = (CONTENT / f"{principle}.md").read_text(encoding="utf-8")
    missing = [s for s in REQUIRED_SECTIONS if s not in text]
    assert not missing, f"{principle}.md is missing {missing}"


@pytest.mark.parametrize("principle", ALL_PRINCIPLES)
def test_each_lesson_declares_matching_front_matter(principle: str) -> None:
    text = (CONTENT / f"{principle}.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{principle}.md has no front matter"
    assert f"id: {principle}" in text, f"{principle}.md front matter id does not match its filename"
