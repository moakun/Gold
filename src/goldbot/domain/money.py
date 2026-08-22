"""Exact decimal arithmetic for the whole decision path.

Every price, cash amount, and risk figure in this system is a `Decimal` created
under one pinned context. Floats are rejected on construction rather than
tolerated, because a float that sneaks into a price is the kind of bug that
makes two runs of the same backtest disagree in the fourth decimal place and
then disagree about a trade.

Reproducibility (FR-020, SC-004) depends on this module being boring.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, setcontext

#: The one context. 28 digits is ample for prices under $10,000 with 4 decimals
#: and accumulated P&L; banker's rounding avoids the upward bias of ROUND_HALF_UP
#: over thousands of fills.
DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)

setcontext(DECIMAL_CONTEXT)

ZERO = Decimal("0")
ONE = Decimal("1")

#: Money is quantised to cents, prices to four places. ETF quotes are penny
#: increments, but stops derived from ATR multiples are not, so prices keep
#: more precision than the cash they produce.
CENTS = Decimal("0.01")
PRICE_PLACES = Decimal("0.0001")


def dec(value: str | int | Decimal) -> Decimal:
    """Build a Decimal, refusing floats.

    Floats are refused rather than converted because `Decimal(0.1)` is
    0.1000000000000000055511151231257827021181583404541015625, and a system
    that silently accepts that cannot promise byte-identical reruns.
    """
    if isinstance(value, float):
        raise TypeError(
            f"refusing to build a Decimal from the float {value!r}; "
            "pass a string (e.g. dec('312.44')) so the value is exact"
        )
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def money(value: str | int | Decimal) -> Decimal:
    """A cash amount, quantised to cents."""
    return dec(value).quantize(CENTS, context=DECIMAL_CONTEXT)


def price(value: str | int | Decimal) -> Decimal:
    """A price, quantised to four decimal places."""
    return dec(value).quantize(PRICE_PLACES, context=DECIMAL_CONTEXT)


def pct(value: str | int | Decimal) -> Decimal:
    """A proportion expressed as a fraction: 1% is dec('0.01'), not 1."""
    result = dec(value)
    if result < 0:
        raise ValueError(f"proportion may not be negative: {result}")
    return result


def fmt_money(value: Decimal) -> str:
    """Render a cash amount for a human reading the journal."""
    return f"{money(value):,.2f}"


def fmt_price(value: Decimal) -> str:
    """Render a price, trimming trailing zeros beyond two places."""
    quantised = price(value)
    trimmed = quantised.normalize()
    exponent = trimmed.as_tuple().exponent
    if isinstance(exponent, int) and exponent > -2:
        trimmed = quantised.quantize(CENTS, context=DECIMAL_CONTEXT)
    return f"{trimmed:f}"
