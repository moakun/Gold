"""The rule registry.

Every rule the strategy can use is listed here. `tests/constitution/
test_no_orphan_principles.py` walks this list and asserts each principle has a
lesson — so adding a rule without teaching the concept behind it fails the
suite, which is the constitution's rule-and-lesson pairing made executable.
"""

from __future__ import annotations

from goldbot.strategy.rules.atr_stop import AtrStop
from goldbot.strategy.rules.entry_trigger import EntryTrigger
from goldbot.strategy.rules.event_blackout import EventBlackout
from goldbot.strategy.rules.trend_exit import TrendExit
from goldbot.strategy.rules.trend_filter import TrendFilter

ALL_RULE_CLASSES = (
    TrendFilter,
    EntryTrigger,
    AtrStop,
    EventBlackout,
    TrendExit,
)

ALL_PRINCIPLES = tuple(sorted({cls.principle for cls in ALL_RULE_CLASSES}))

__all__ = [
    "ALL_PRINCIPLES",
    "ALL_RULE_CLASSES",
    "AtrStop",
    "EntryTrigger",
    "EventBlackout",
    "TrendExit",
    "TrendFilter",
]
