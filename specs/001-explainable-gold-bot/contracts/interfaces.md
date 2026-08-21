# Contract: Internal Interfaces

**Feature**: 001-explainable-gold-bot | **Date**: 2026-08-21

These are the seams the architecture depends on. Each carries invariants that a constitution
principle relies upon, so they are contracts rather than implementation details — changing a
signature here is a governance question, not a refactor.

Signatures are `typing.Protocol` definitions. Each is followed by the invariants implementations
must uphold and the test that enforces them.

## `Rule`

```python
class Rule(Protocol):
    rule_id: str
    principle: str

    def evaluate(self, view: MarketView) -> Verdict: ...
```

**Invariants**

1. Returns exactly one `Verdict`, always — never `None`, never raises for an ordinary "condition
   not met". Failure to meet a condition is a `Verdict` with `passed=False`, which is what makes
   FR-004 possible.
2. `Verdict.evidence` contains the actual values compared, not a summary.
3. `Verdict.statement` reads as a sentence to someone who does not know the strategy (FR-008).
4. Pure: no I/O, no wall-clock, no randomness. Given the same `MarketView`, returns the same
   `Verdict`.
5. `principle` resolves to a lesson file.

**Enforced by**: `tests/constitution/test_rules_are_pure.py` (no forbidden imports reachable from
`strategy/`), and `test_no_orphan_principles.py` which enumerates every registered rule and
asserts a matching lesson exists.

## `MarketView`

```python
class MarketView(Protocol):
    as_of: datetime

    def __getitem__(self, i: int) -> Bar: ...
    def window(self, n: int) -> tuple[Bar, ...]: ...
    def latest(self) -> Bar: ...
```

**Invariants**

1. No accessor returns a bar whose `end > as_of`. Attempting it raises `LookAheadError`.
2. Negative indexing counts back from the decision bar, never forward from the start.
3. `window(n)` returns at most `n` bars and never pads — a rule needing 200 bars on bar 50 gets 50
   and must handle it in its `Verdict` (typically `passed=False` with a "insufficient history"
   statement).

**Enforced by**: `tests/constitution/test_no_lookahead.py`, which drives a deliberately cheating
rule against a view and asserts it raises.

This is the interface that makes FR-022 real. Everything else about backtest honesty follows from
it.

## `DataFeed`

```python
class DataFeed(Protocol):
    def bars(self) -> Iterator[Bar]: ...
    def snapshot_digest(self) -> str | None: ...
```

**Invariants**

1. Yields bars in ascending time order, with no duplicate `end` timestamps.
2. Yields only `is_complete=True` bars to the engine; partial bars are filtered at the feed
   boundary, not left for the engine to remember to check.
3. Gaps are surfaced as an explicit `DataGap` event, never interpolated (missing-data edge case).
4. `HistoricalFeed` returns a digest; `LiveFeed` returns `None`. A backtest with a `None` digest
   is refused — reproducibility requires pinned data (FR-020).

## `Clock`

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
    def next_session_open(self, after: datetime) -> datetime: ...
```

**Invariants**

1. `HistoricalClock.now()` derives from the current bar, never from the system clock.
2. `next_session_open` consults the exchange calendar — it steps over weekends, holidays, and
   early closes (FR-038, research.md R6).
3. All returns are UTC-aware.

**Enforced by**: `tests/constitution/test_no_wallclock.py` — no module under `strategy/`, `risk/`,
or `engine/` may reference `datetime.now` or `time.time` outside the `LiveClock` implementation.

## `RiskGate`

```python
class RiskGate(Protocol):
    def authorize(
        self, decision: Decision, account: AccountState
    ) -> Authorization | Rejection: ...
```

**Invariants** — this is the load-bearing interface for Principle I.

1. **`Authorization` has no public constructor.** `RiskGate.authorize` is its only source. A
   caller cannot fabricate one.
2. Checks, all of which must pass: symbol on the allow-list (FR-009); a stop is present and on
   the correct side of entry (FR-012); sized risk ≤ per-trade limit (FR-013); daily loss halt not
   tripped (FR-014); kill-switch latch not set; concurrent-position limit respected.
3. A `Rejection` carries the same explanatory quality as a `Verdict` — rule, evidence, and a human
   statement. A refused trade is a teaching moment, not an error log line.
4. Every call is recorded, authorized or not. Rejections are evidence that the guards work.

**Enforced by**: `tests/unit/risk/` rejection-path tests, written before the guards they cover, per
the constitution's workflow section. Plus `tests/constitution/test_authorization_unforgeable.py`.

## `Broker`

```python
class Broker(Protocol):
    def submit(self, auth: Authorization) -> Fill | Rejection: ...
    def flatten_all(self) -> Sequence[Fill]: ...
```

**Invariants**

1. **Accepts `Authorization`, not `Order`.** There is no way to submit something the risk gate has
   not signed.
2. `SimulatedBroker` is the only implementation in this version. No network I/O occurs in this
   module.
3. Fills model spread, commission, and slippage. A fill at exactly the intended price with zero
   cost is a bug (FR-021).
4. Gap handling: when the next session opens beyond the stop, the fill price is the open, not the
   stop, and `Trade.risk_overrun` records the difference. Stops are intentions, not guarantees.

**Enforced by**: `tests/constitution/test_no_live_broker.py` — asserts that no brokerage trading
SDK appears in the lockfile and that `Broker` has exactly one implementation.

## `AuditStore`

```python
class AuditStore(Protocol):
    def record_decision(self, d: Decision) -> None: ...
    def record_fill(self, f: Fill) -> None: ...
    def record_violation(self, v: Violation) -> None: ...
    def decisions_on(self, date: date) -> Sequence[Decision]: ...
```

**Invariants**

1. Append-only, enforced by database triggers rather than by the method surface (FR-025).
2. Writes happen before the action they describe, not after. A crash between decision and
   execution leaves a recorded decision with no fill — recoverable and honest. The reverse would
   be an unexplained trade.
3. No method accepts credentials, and no recorded field may contain one (FR-028).

## `Explainer`

```python
class Explainer(Protocol):
    def render(self, decision: Decision) -> str: ...
```

**Invariants**

1. Renders **only** from `decision.verdicts`. It has no access to outcomes, later bars, or
   performance. An explainer that could see results would be writing narration, which the spec
   forbids.
2. Deterministic: same decision, same text.
3. Never returns empty. A `Decision` that renders to nothing fails construction upstream (FR-006).

**Enforced by**: `tests/constitution/test_explainer_isolation.py` — the explainer's signature
admits nothing but a `Decision`, and a test asserts the rendered text mentions every failed
verdict for a `SKIP`.
