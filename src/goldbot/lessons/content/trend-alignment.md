---
id: trend-alignment
title: Trend Alignment
---

## What it is

Only take trades in the direction the market has already been moving over a
long window. Here that means: no long is considered unless price is above its
100-day average.

This is not a prediction. The average does not know anything. What it does is
divide history into two regimes and decline to trade in one of them. The claim
is modest and empirically decent: markets that have been rising tend to keep
rising slightly more often than chance, and — more importantly — the really
ugly declines almost all happen below the long average.

## When it works

It earns its keep in sustained moves, which is precisely when the money is
made. A trend filter keeps you in for the whole of a long advance and out of
the whole of a long decline, and since a handful of big moves account for most
of any strategy's return, being present for them matters more than being clever
in between.

It also works as a **behavioural** control. The trades it forbids are the ones
that feel most compelling: the market is down a lot, it looks cheap, surely
this is the bottom. The filter does not argue with that feeling. It just does
not let it place an order.

## When it fails

Three ways, and all three will happen to you:

1. **Whipsaw.** In a sideways market price crosses the average repeatedly, and
   the filter flips from permissive to forbidding and back, generating small
   losses on both sides. This is the common case, not the exception —
   most of the time markets are not trending.
2. **Late entry.** By definition you cannot be long until price is already
   above a 100-day average, so you miss the first leg of every recovery. That
   is the price of the protection, not a flaw to be optimised away.
3. **Lookback sensitivity.** 100 days works; so does 150; so does 200. If your
   results change dramatically between them, you have not found an edge, you
   have found a coincidence. Testing three lookbacks and keeping the best one
   is how backtests get overfit.

## In gold

Gold trends unusually well, and unusually long. Its drivers — real interest
rates, the dollar, central-bank buying, and periodic flights to safety — are
slow-moving macro forces rather than quarterly earnings, so when they turn they
tend to stay turned for months or years. That makes a long trend filter a
better fit for gold than for, say, an individual equity.

The flip side is that gold can also do nothing for years at a time. From 2013
to 2018 it spent most of its life going sideways, and a trend filter in that
period mostly produced small losses and the correct instruction to stay out.
The filter was working. That is what working looks like a lot of the time.

One gold-specific caution: because this system trades an ETF rather than the
metal, the average is computed on the fund's share price. Over long horizons
the fund's fee causes a small persistent drag relative to spot gold. It is
already in the price series, and therefore already in the average — which is
exactly why signals and execution must come from the same series.
