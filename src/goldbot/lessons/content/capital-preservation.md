---
id: capital-preservation
title: Capital Preservation
---

## What it is

Survive first. Returns are what happens to accounts that are still trading.

Concretely: risk at most 1% of equity on any single trade, stop for the session
after losing 3%, hold one position at a time, and never widen a stop or add to
a loser. These limits are enforced in code rather than intended, because the
moment they matter most is the moment you will most want to override them.

The arithmetic behind the caution is the part people underestimate. Losses and
the gains needed to recover them are not symmetric:

| Drawdown | Gain needed to get back |
|---|---|
| 10% | 11% |
| 25% | 33% |
| 50% | 100% |
| 75% | 300% |

A 50% loss does not need a 50% gain. It needs a double. This is why a strategy
that makes 20% a year and occasionally loses 60% is worse than one that makes
8% a year and never loses more than 15% — and why the second is far easier to
keep following.

## When it works

Always, in the sense that it always does what it says. The interesting question
is what it costs, and the answer is: it caps your best year. A 1% risk limit
means you cannot make a fortune on one brilliant trade.

That is the trade being made deliberately. Position sizing this conservative
turns trading from a series of bets into a process with a survivable variance,
which is the only version of it you can run for years and learn anything from.

## When it fails

**It cannot stop a gap.** The 1% limit assumes the stop fills at its price. For
an instrument closed most of the day, sometimes it does not. See
[[volatility-based-stops]] — the real distribution of losses has a right tail
the limit does not control.

**It cannot stop correlated risk.** One position at a time protects against
concentration in this system, but if you also hold gold miners in another
account, your actual exposure is not what this system thinks it is.

**Limits do not survive being edited.** The most dangerous version of this
failure is a person, after three losing trades, deciding the limit is too
conservative. The constitution puts the numbers behind an amendment process for
exactly that reason, and the risk envelope is immutable while a session runs.

## In gold

Gold is less volatile than equities on average and considerably more volatile
than most people expect during regime changes. Daily moves of 2–3% are
unremarkable when policy expectations shift, and 5% days happen.

For an account trading a ~$300 ETF share, two constraints interact awkwardly:
whole-share sizing and the 1% rule. Below roughly $5,000 of equity, one share
can be several percent of the account, so the 1% limit becomes approximate at
best — the system warns about this at startup rather than letting you discover
it in a confusing journal entry. See [[position-sizing]].

The daily loss halt is worth understanding in this context. On a swing strategy
holding for days or weeks, it is evaluated against *realised* losses within the
session, not unrealised drawdown on an open position. Otherwise an ordinary
adverse day in a healthy trade would trip it, and the stop is already the
control for that exposure.
