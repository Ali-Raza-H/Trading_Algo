from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading_bot.connectors.base import BrokerConnector
from trading_bot.data.features import compute_features


@dataclass(frozen=True)
class CandleBundle:
    symbol: str
    candles: pd.DataFrame
    features: dict[str, Any]


class DataPipeline:
    def __init__(self, connector: BrokerConnector, *, timeframe: str, warmup_bars: int) -> None:
        self.connector = connector
        self.timeframe = timeframe
        self.warmup_bars = warmup_bars
        self._log = logging.getLogger("trading_bot.pipeline")

    def fetch(self, symbol: str) -> CandleBundle:
        df = self.connector.get_candles(symbol, self.timeframe, self.warmup_bars)
        if df is None or df.empty:
            return CandleBundle(symbol=symbol, candles=pd.DataFrame(), features={})
        feats = compute_features(df)
        return CandleBundle(symbol=symbol, candles=df, features=feats)

