from __future__ import annotations

from dataclasses import dataclass

from trading_bot.strategies.base import StrategyBase
from trading_bot.strategies.range_mean_reversion import RangeMeanReversionStrategy
from trading_bot.strategies.two_pole_momentum import TwoPoleMomentumStrategy


@dataclass(frozen=True)
class StrategyRegistry:
    strategies: dict[str, StrategyBase]

    @classmethod
    def default(cls) -> "StrategyRegistry":
        items: list[StrategyBase] = [
            TwoPoleMomentumStrategy(),
            RangeMeanReversionStrategy(),
        ]
        return cls(strategies={s.name: s for s in items})

    def get(self, name: str) -> StrategyBase:
        if name not in self.strategies:
            raise KeyError(f"Unknown strategy: {name}. Available: {sorted(self.strategies)}")
        return self.strategies[name]

