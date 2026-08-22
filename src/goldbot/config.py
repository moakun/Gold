"""Loading and versioning configuration.

Everything numeric arrives as a string in the TOML and becomes a `Decimal`
here. That is deliberate: TOML floats would smuggle binary floating point into
prices, and reproducibility depends on them being exact.

The config is content-hashed. Every run records the hash, so a result can
always be traced back to the exact settings that produced it.
"""

from __future__ import annotations

import hashlib
import os
import tomllib
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from goldbot.domain.envelope import RiskEnvelope
from goldbot.domain.errors import ConfigError
from goldbot.domain.instrument import AllowList, Instrument
from goldbot.domain.money import dec


@dataclass(frozen=True, slots=True)
class StrategyParams:
    """Tunables for the rule set. Deliberately few — more knobs, more overfitting."""

    trend_lookback: int = 100
    momentum_lookback: int = 20
    atr_lookback: int = 14
    atr_stop_multiple: Decimal = dec("2.0")
    reward_risk_target: Decimal = dec("2.0")
    min_history: int = 100

    def __post_init__(self) -> None:
        for name in ("trend_lookback", "momentum_lookback", "atr_lookback", "min_history"):
            if getattr(self, name) < 1:
                raise ConfigError(f"{name} must be at least 1")
        if self.atr_stop_multiple <= 0:
            raise ConfigError("atr_stop_multiple must be positive")
        if self.reward_risk_target <= 0:
            raise ConfigError("reward_risk_target must be positive")


@dataclass(frozen=True, slots=True)
class EventPolicy:
    """What to do around scheduled high-impact releases (FR-019).

    An explicit policy, never left to chance. Standing aside through an FOMC
    decision is a choice; wandering into one without noticing is not.
    """

    policy: str = "stand_aside"
    blackout_dates: tuple[date, ...] = ()

    def __post_init__(self) -> None:
        allowed = {"stand_aside", "reduce_size", "trade"}
        if self.policy not in allowed:
            raise ConfigError(f"event policy must be one of {sorted(allowed)}, got {self.policy!r}")

    def is_blackout(self, day: date) -> bool:
        return day in self.blackout_dates


@dataclass(frozen=True)
class Config:
    symbol: str
    cadence: str
    initial_equity: Decimal
    allow_list: AllowList
    envelope: RiskEnvelope
    strategy: StrategyParams
    events: EventPolicy
    version: str
    source_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def instrument(self) -> Instrument:
        return self.allow_list.require(self.symbol)


def _require(table: dict[str, Any], key: str, where: str) -> Any:
    if key not in table:
        raise ConfigError(f"missing [{where}] {key}")
    return table[key]


def _decimal(table: dict[str, Any], key: str, default: str | None = None) -> Decimal:
    value = table.get(key, default)
    if value is None:
        raise ConfigError(f"missing decimal value for {key}")
    if isinstance(value, float):
        raise ConfigError(
            f"{key} is a TOML float ({value}); write it as a quoted string so the value is "
            'exact, e.g. {key} = "0.010"'.replace("{key}", key)
        )
    return dec(str(value))


def load_config(path: Path) -> Config:
    """Read a config file into typed, validated objects."""
    if not path.exists():
        raise ConfigError(f"no config at {path}")
    payload = path.read_bytes()
    raw = tomllib.loads(payload.decode("utf-8"))

    run = raw.get("run", {})
    symbol = str(_require(run, "symbol", "run")).upper()
    cadence = str(run.get("cadence", "daily")).lower()
    if cadence not in {"daily", "4h"}:
        raise ConfigError(f"cadence must be 'daily' or '4h', got {cadence!r}")

    instruments_table = raw.get("instruments", {})
    if not instruments_table:
        raise ConfigError("config must define at least one [instruments.SYMBOL] table")

    instruments: list[Instrument] = []
    for sym, spec in sorted(instruments_table.items()):
        instruments.append(
            Instrument(
                symbol=sym.upper(),
                name=str(spec.get("name", sym)),
                calendar=str(spec.get("calendar", "XNYS")),
                expense_ratio=_decimal(spec, "expense_ratio", "0.0040"),
                commission_per_share=_decimal(spec, "commission_per_share", "0"),
                commission_minimum=_decimal(spec, "commission_minimum", "0"),
                half_spread_bps=_decimal(spec, "half_spread_bps", "1.0"),
                slippage_bps=_decimal(spec, "slippage_bps", "2.0"),
            )
        )
    allow_list = AllowList(tuple(instruments))

    risk = raw.get("risk", {})
    envelope = RiskEnvelope(
        max_risk_per_trade=_decimal(risk, "max_risk_per_trade", "0.010"),
        max_daily_loss=_decimal(risk, "max_daily_loss", "0.030"),
        max_concurrent_positions=int(risk.get("max_concurrent_positions", 1)),
        max_leverage=_decimal(risk, "max_leverage", "2.0"),
    )

    strategy_table = raw.get("strategy", {})
    strategy = StrategyParams(
        trend_lookback=int(strategy_table.get("trend_lookback", 100)),
        momentum_lookback=int(strategy_table.get("momentum_lookback", 20)),
        atr_lookback=int(strategy_table.get("atr_lookback", 14)),
        atr_stop_multiple=_decimal(strategy_table, "atr_stop_multiple", "2.0"),
        reward_risk_target=_decimal(strategy_table, "reward_risk_target", "2.0"),
        min_history=int(strategy_table.get("min_history", 100)),
    )

    events_table = raw.get("events", {})
    events = EventPolicy(
        policy=str(events_table.get("policy", "stand_aside")),
        blackout_dates=tuple(
            date.fromisoformat(str(d)) for d in events_table.get("blackout_dates", [])
        ),
    )

    return Config(
        symbol=symbol,
        cadence=cadence,
        initial_equity=_decimal(run, "initial_equity", "100000.00"),
        allow_list=allow_list,
        envelope=envelope,
        strategy=strategy,
        events=events,
        version=hashlib.sha256(payload).hexdigest()[:12],
        source_path=path,
        raw=raw,
    )


def credential(name: str) -> str | None:
    """Read a credential from the environment. Never from a file, never a literal.

    Returns None rather than raising, so the caller can explain what the missing
    credential would have enabled. The default daily path needs none of these.
    """
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None
