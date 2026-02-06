from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from trading_bot.connectors.base import Position, Quote, Side, SymbolMeta


@dataclass(frozen=True)
class Signal:
    side: Side
    confidence: float
    reason: str
    suggested_sl: float | None = None
    suggested_tp: float | None = None
    tags: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyContext:
    symbol: str
    timeframe: str
    candle_close_time_utc: str
    quote: Quote | None
    symbol_meta: SymbolMeta | None
    current_position: Position | None


class StrategyBase(ABC):
    name: str

    @abstractmethod
    def generate_signal(
        self,
        *,
        candles: pd.DataFrame,
        features: dict[str, Any],
        ctx: StrategyContext,
    ) -> Signal:
        raise NotImplementedError

