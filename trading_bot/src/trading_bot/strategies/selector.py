from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.core.config import StrategyConfig
from trading_bot.strategies.base import StrategyBase
from trading_bot.strategies.registry import StrategyRegistry


@dataclass(frozen=True)
class StrategySelection:
    strategy: StrategyBase | None
    name: str | None
    reason: str


class StrategySelector:
    def __init__(self, cfg: StrategyConfig, registry: StrategyRegistry) -> None:
        self.cfg = cfg
        self.registry = registry

    def select(self, features: dict[str, Any]) -> StrategySelection:
        if self.cfg.mode == "manual":
            s = self.registry.get(self.cfg.manual_active)
            return StrategySelection(strategy=s, name=s.name, reason="manual mode")

        adx = float(features.get("adx14") or 0.0)
        trending = float(self.cfg.rule_based.adx_trending)
        ranging = float(self.cfg.rule_based.adx_ranging)

        if adx >= trending:
            s = self.registry.get("two_pole_momentum")
            return StrategySelection(strategy=s, name=s.name, reason=f"ADX {adx:.1f} >= {trending:.1f} (trending)")
        if adx <= ranging:
            s = self.registry.get("range_mean_reversion")
            return StrategySelection(strategy=s, name=s.name, reason=f"ADX {adx:.1f} <= {ranging:.1f} (ranging)")

        return StrategySelection(strategy=None, name=None, reason=f"ADX {adx:.1f} mid-zone: no trade")

