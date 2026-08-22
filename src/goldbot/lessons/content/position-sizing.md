---
id: position-sizing
title: Position Sizing
---

## What it is

The stop decides where you are wrong. The size decides how much that costs.
Working out the second from the first is position sizing, and it is the single
highest-leverage habit in trading:

```
shares = (equity x risk_limit) / (entry - stop)
```

Risking 1% of a $100,000 account with a $4 stop distance means 250 shares.
Widen the stop to $8 and it means 125. The loss at the stop is $1,000 either
way, which is the whole point: **every trade risks the same amount regardless
of how far away the invalidation level sits.**

Most people do this backwards. They pick a size that feels right — "I'll buy
100 shares" — and then place a stop wherever it seems reasonable, which makes
the risk on each trade an accident.

## When it works

It makes results comparable. When every trade risks 1%, a run of outcomes can
be read as a distribution: this many losers at -1R, these winners at +2.4R,
+1.8R, and so on. Expectancy becomes computable and a losing streak becomes
survivable arithmetic rather than a crisis.

It also decouples conviction from exposure. You cannot bet more because you
feel strongly — the stop and the account decide, and neither has feelings.

## When it fails

**Whole shares quantise it.** You cannot buy 33.7 shares at most brokers, so
the formula rounds down and actual risk lands below the limit. On a large
account the rounding is noise. On a small one it is the dominant effect.

**Cash binds before risk does.** With a tight stop the formula happily asks for
more shares than you can pay for. A $10,000 account risking 1% ($100) with a $3
stop wants 33 shares, which at $300 a share costs $9,900 — nearly everything.
The system takes the smaller of the two and records which constraint bound, so
the journal tells you *why* the position is the size it is.

**Sometimes the answer is zero.** If a single share would risk more than the
limit allows, there is no valid position. The system reports a skip with that
reason. It is correct and it is annoying, and the fix is a wider account, not
a wider limit.

## In gold

Gold ETF shares are expensive relative to a small account, so the cash
constraint bites more often here than it would trading a $30 stock. Expect the
journal to name `AVAILABLE_CASH` as the binding constraint regularly if you are
running a modest balance.

There is a rough threshold worth knowing: **below about $5,000 of equity, the
1% rule stops meaning much** on a ~$300 share. One share is 6% of the account
in notional terms, and while the *risk* is only the stop distance, the
quantisation means your actual per-trade risk jumps around in large steps
rather than sitting near the limit.

Gold's volatility also feeds directly into size through the ATR-based stop.
When volatility doubles, stop distance doubles and size halves automatically.
That is the machinery working, and it means the position is smallest exactly
when the market is most dangerous — which is the opposite of what most people
do unaided. See [[volatility-based-stops]] and [[capital-preservation]].
