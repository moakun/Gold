---
id: volatility-based-stops
title: Volatility-Based Stops
---

## What it is

Put the stop where the idea is wrong, not where the loss feels tolerable — and
scale that distance to how much the market is currently moving. Here: two times
the 14-day average true range below the entry.

Average true range measures the typical daily travel, including the overnight
gap. Two ATRs is roughly "further than this market normally moves against me in
a day or two". Price reaching it is therefore weak evidence that something has
changed, rather than a coin landing badly.

The stop then determines the position size, never the other way round. Wider
stop, fewer shares. This is the mechanism that keeps every trade risking the
same 1%, whether the market is calm or violent.

## When it works

It adapts. During calm periods stops tighten and size grows; during turbulence
stops widen and size shrinks automatically. You end up taking roughly constant
risk, which is what makes a string of results comparable to each other — and
comparability is what lets you learn anything from them at all.

It also removes a decision you are bad at making. Choosing a stop in the moment
means choosing between "close enough that I won't lose much" and "far enough
that I won't get shaken out", and under pressure people reliably pick the
former and then move it.

## When it fails

**Volatility clusters and regime-shifts.** ATR is backward-looking. When
volatility jumps, the ATR computed from the previous fortnight is too small,
and the stop placed from it is too tight — exactly at the moment you most
needed room.

**Wide stops shrink positions to nothing.** In a violent market, two ATRs may
be so wide that a 1% risk budget buys one share, or none. The system reports
that as a skip with a reason. It is the correct answer and it is frustrating.

**The stop is not a guarantee.** This is the important one, so it has its own
section below.

## In gold

Gold has a specific and uncomfortable property for stop placement: it is a
24-hour market that this system trades through a fund open six and a half
hours a day. Gold trades in London and Asia while the ETF does not. A macro
event overnight moves the metal, and the fund simply opens somewhere else in
the morning.

The consequence is that **a stop is an intention, not a guarantee.** If your
stop is at 196 and the fund opens at 191, you exit at 191. The 1% you planned to
risk becomes 2%, or worse. This is not a bug in the system and it cannot be
engineered away by trading a share that is closed most of the day.

What the system does about it: `Trade.risk_overrun` records how much each loss
exceeded its plan, and the performance report shows the count. A backtest
reporting zero overruns across years of daily bars is not reassuring — it means
the fill model is assuming stops always execute at their price, which flatters
every number in the report.

Including the gap term in true range helps a little: it means the ATR already
reflects that this instrument gaps, so stops are wider than a session-only
measure would suggest. It is a mitigation, not a solution.
