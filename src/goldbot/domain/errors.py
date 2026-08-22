"""The exception hierarchy.

These are deliberately distinct types rather than one generic error, because
the CLI maps them to different exit codes (contracts/cli.md) and the difference
matters: bad data, a guard firing, and a deliberate halt are three very
different things for an operator to see at 4pm.
"""

from __future__ import annotations


class GoldbotError(Exception):
    """Base for everything this system raises deliberately."""


class DataIntegrityError(GoldbotError):
    """The data is wrong: digest mismatch, gapped bars, impossible OHLC.

    Exit code 3.
    """


class GuardViolation(GoldbotError):
    """A guard fired: the code tried something the constitution forbids.

    Exit code 4. This is the most important failure class in the system — it
    means a rule, a caller, or a config asked for something that would breach
    Principle I or II, and the attempt was refused.
    """


class LookAheadError(GuardViolation):
    """Something tried to read a bar that had not happened yet.

    A subclass of GuardViolation because peeking at the future is not a
    programming inconvenience, it is the single most effective way to produce a
    backtest that lies.
    """


class HaltRequired(GoldbotError):
    """The system stopped itself: SAFE mode, daily loss limit, or kill switch.

    Exit code 5. Not an error in the sense of something going wrong — this is
    the machinery working.
    """


class ConfigError(GoldbotError):
    """The configuration is unusable. Exit code 2."""
