---
id: event-risk
title: Event Risk
---

## What it is

Some price moves come from information the strategy has no view on. A central
bank rate decision, an inflation print, an employment report: the market knows
the announcement is coming, knows roughly when, and does not know what it will
say. Positioning into that is not trading a trend, it is taking a position on
a coin flip.

The policy here is to stand aside on scheduled high-impact dates. Two other
policies are defensible and configurable — reduce size, or trade through — but
the requirement is that you pick one deliberately rather than discovering after
the fact that you were holding through the FOMC.

## When it works

Standing aside converts a fat-tailed outcome into no outcome. Over many events
this trims both the best and worst results, and since the risk system cares far
more about the left tail than the right, that trade is usually worth making.

It works particularly well for strategies whose edge is trend persistence.
Trend following makes money from moves that unfold over weeks; event moves
unfold in seconds and frequently reverse. Those are not the same phenomenon,
and a system built for one has no business collecting the other.

## When it fails

**You miss real moves.** Some of the largest and most durable trends *start* on
event days, because the event is what changed the macro picture. Standing aside
means entering later and worse, or missing the move entirely.

**The blackout list is manual and will go stale.** This system takes the dates
from configuration rather than fetching a calendar, because a rule that calls an
API is no longer a pure, reproducible function of the market. The cost is that
an empty or outdated list silently means "no event risk", which is never true.
Check it.

**Unscheduled shocks are not covered at all.** A geopolitical event on a
Saturday is not on any list. The blackout rule handles the known unknowns; the
stop and the position size handle everything else, imperfectly.

## In gold

Gold is unusually event-sensitive because its price is largely a function of
real interest rates and the dollar, and both are set by exactly the
announcements on the blackout list. A US inflation surprise moves gold twice —
once through the inflation number itself, and again through what it implies
about policy.

The three dates that matter most:

- **FOMC decisions and the accompanying projections.** Gold's single biggest
  scheduled mover, because it is a direct read on real rates.
- **CPI releases.** Both the print and the market's revised policy expectation.
- **Non-farm payrolls.** Same channel, one step removed.

There is an honest tension here with momentum confirmation, which fires most
often on days when something has just happened. The system's compromise — stand
aside on scheduled events, accept unscheduled ones — is a judgement call, not a
derivation. Reasonable people run this differently, and the config lets you.
