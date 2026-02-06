from __future__ import annotations

from typing import Any

import pandas as pd

from trading_bot.connectors.base import Side
from trading_bot.core.utils import clamp
from trading_bot.strategies.base import Signal, StrategyBase, StrategyContext


class RangeMeanReversionStrategy(StrategyBase):
    name = "range_mean_reversion"

    def generate_signal(
        self,
        *,
        candles: pd.DataFrame,
        features: dict[str, Any],
        ctx: StrategyContext,
    ) -> Signal:
        rsi14 = features.get("rsi14")
        if rsi14 is None:
            return Signal(side=Side.FLAT, confidence=0.0, reason="RSI not available")
        rsi14 = float(rsi14)

        pos = ctx.current_position
        if pos is not None:
            if pos.side == Side.LONG and rsi14 >= 50:
                conf = clamp((rsi14 - 50.0) / 20.0, 0.0, 1.0)
                return Signal(side=Side.FLAT, confidence=conf, reason="RSI mean reversion: exit long", tags=["exit"])
            if pos.side == Side.SHORT and rsi14 <= 50:
                conf = clamp((50.0 - rsi14) / 20.0, 0.0, 1.0)
                return Signal(side=Side.FLAT, confidence=conf, reason="RSI mean reversion: exit short", tags=["exit"])
            return Signal(side=Side.FLAT, confidence=0.0, reason="In position: no exit signal")

        if rsi14 <= 30:
            conf = clamp((30.0 - rsi14) / 20.0, 0.0, 1.0)
            return Signal(side=Side.LONG, confidence=conf, reason=f"RSI oversold ({rsi14:.1f})")
        if rsi14 >= 70:
            conf = clamp((rsi14 - 70.0) / 20.0, 0.0, 1.0)
            return Signal(side=Side.SHORT, confidence=conf, reason=f"RSI overbought ({rsi14:.1f})")
        return Signal(side=Side.FLAT, confidence=0.0, reason=f"RSI neutral ({rsi14:.1f})")

