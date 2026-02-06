from __future__ import annotations

import json
from datetime import time
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator

from trading_bot.core.exceptions import ConfigError


class RuntimeConfig(BaseModel):
    timezone: str = "Europe/London"
    timeframe: str = "H1"
    evaluation_mode: Literal["on_candle_close"] = "on_candle_close"
    warmup_bars: int = 300
    loop_sleep_seconds: float = 2.0

    @field_validator("warmup_bars")
    @classmethod
    def _warmup_positive(cls, v: int) -> int:
        if v < 50:
            raise ValueError("warmup_bars must be >= 50")
        return v

    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


class UniverseAssetClasses(BaseModel):
    forex: bool = True
    metals: bool = True
    indices: bool = True
    stocks: bool = True


class UniverseDiscoveryLimits(BaseModel):
    max_symbols_total: int = 40
    max_per_class: int = 20


class UniverseConfig(BaseModel):
    use_symbol_discovery: bool = True
    discovery_interval_minutes: int = 360
    preferred_symbols: list[str] = Field(default_factory=list)
    include_asset_classes: UniverseAssetClasses = Field(
        default_factory=UniverseAssetClasses
    )
    discovery_limits: UniverseDiscoveryLimits = Field(default_factory=UniverseDiscoveryLimits)


class RankingFilters(BaseModel):
    max_spread_points: int = 50
    max_spread_to_atr_ratio: float = 0.20
    market_open_required: bool = True


class RankingWeights(BaseModel):
    volatility: float = 0.35
    trend: float = 0.30
    momentum: float = 0.20
    cost: float = 0.15

    @field_validator("volatility", "trend", "momentum", "cost")
    @classmethod
    def _weight_bounds(cls, v: float) -> float:
        if v < 0:
            raise ValueError("weights must be >= 0")
        return v


class RankingCorrelation(BaseModel):
    enabled: bool = True
    window_bars: int = 200
    max_abs_corr: float = 0.85


class RankingConfig(BaseModel):
    top_n: int = 5
    min_bars_required: int = 300
    filters: RankingFilters = Field(default_factory=RankingFilters)
    weights: RankingWeights = Field(default_factory=RankingWeights)
    correlation: RankingCorrelation = Field(default_factory=RankingCorrelation)


class StrategyRuleBased(BaseModel):
    adx_trending: float = 22
    adx_ranging: float = 18


class StrategyConfig(BaseModel):
    mode: Literal["manual", "rule_based"] = "manual"
    manual_active: str = "two_pole_momentum"
    rule_based: StrategyRuleBased = Field(default_factory=StrategyRuleBased)


class RiskRRConfig(BaseModel):
    stop_points: int = 100
    take_points: int = 200


class RiskATRConfig(BaseModel):
    period: int = 14
    sl_mult: float = 1.5
    tp_mult: float = 3.0


class RiskCooloffConfig(BaseModel):
    enabled: bool = True
    losses: int = 3
    minutes: int = 120


class RiskConfig(BaseModel):
    risk_per_trade: float = 0.005
    max_daily_loss_pct: float = 0.02
    max_drawdown_pct: float = 0.06
    max_open_positions_total: int = 5
    max_open_positions_per_symbol: int = 1
    close_positions_on_breach: bool = False
    sltp_mode: Literal["rr", "atr"] = "rr"
    rr: RiskRRConfig = Field(default_factory=RiskRRConfig)
    atr: RiskATRConfig = Field(default_factory=RiskATRConfig)
    cooloff: RiskCooloffConfig = Field(default_factory=RiskCooloffConfig)


class ExecutionRetries(BaseModel):
    max_attempts: int = 3
    backoff_seconds: list[float] = Field(default_factory=lambda: [1, 3, 7])


class ExecutionConfig(BaseModel):
    trading_enabled: bool = False
    close_on_exit_signal: bool = True
    order_type: Literal["market"] = "market"
    slippage_points: int = 20
    magic_number: int = 26012026
    retries: ExecutionRetries = Field(default_factory=ExecutionRetries)


class NotificationsConfig(BaseModel):
    telegram_enabled: bool = True
    throttle_seconds: int = 20
    daily_summary_time: str = "21:00"

    def daily_summary_time_obj(self) -> time:
        hh, mm = self.daily_summary_time.split(":")
        return time(hour=int(hh), minute=int(mm))


class PersistenceConfig(BaseModel):
    db_path: str = "./data/bot.sqlite"


class UIConfig(BaseModel):
    enabled: bool = True
    refresh_hz: float = 2.0


class AppConfig(BaseModel):
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    universe: UniverseConfig = Field(default_factory=UniverseConfig)
    ranking: RankingConfig = Field(default_factory=RankingConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    ui: UIConfig = Field(default_factory=UIConfig)

    def redacted_dict(self) -> dict[str, Any]:
        return self.model_dump()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except Exception as exc:
        raise ConfigError(f"Failed reading config yaml: {path}") from exc


def load_config(
    config_path: str | Path,
    db_latest_settings_json: str | None = None,
) -> AppConfig:
    load_dotenv(override=False)
    path = Path(config_path)
    raw = load_yaml(path)

    if db_latest_settings_json:
        try:
            override = json.loads(db_latest_settings_json)
            if isinstance(override, dict):
                raw = _deep_merge_dicts(raw, override)
        except Exception:
            # If snapshot is corrupted, ignore it; engine will still run.
            pass

    try:
        return AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc


def _deep_merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge_dicts(out[k], v)
        else:
            out[k] = v
    return out

