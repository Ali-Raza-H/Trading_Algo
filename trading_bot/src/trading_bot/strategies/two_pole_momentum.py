from __future__ import annotations

from typing import Any

import pandas as pd

from trading_bot.connectors.base import Side
from trading_bot.core.utils import clamp
from trading_bot.strategies.base import Signal, StrategyBase, StrategyContext


class TwoPoleMomentumStrategy(StrategyBase):
    name = "two_pole_momentum"

    def generate_signal(
        self,
        *,
        candles: pd.DataFrame,
        features: dict[str, Any],
        ctx: StrategyContext,
    ) -> Signal:
        cross = int(features.get("tp_cross") or 0)
        hist = float(features.get("tp_hist") or 0.0)
        atr14 = float(features.get("atr14") or 0.0)
        adx14 = float(features.get("adx14") or 0.0)
        slope = float(features.get("ema50_slope") or 0.0)

        strength = abs(hist) / atr14 if atr14 > 0 else 0.0
        conf = clamp(0.25 + 0.45 * clamp(strength, 0.0, 1.0) + 0.30 * clamp(adx14 / 50.0, 0.0, 1.0), 0.0, 1.0)

        pos = ctx.current_position
        if pos is not None:
            if pos.side == Side.LONG and cross < 0:
                return Signal(side=Side.FLAT, confidence=conf, reason="Two-pole crossover down: exit long", tags=["exit"])
            if pos.side == Side.SHORT and cross > 0:
                return Signal(side=Side.FLAT, confidence=conf, reason="Two-pole crossover up: exit short", tags=["exit"])
            return Signal(side=Side.FLAT, confidence=0.0, reason="In position: no exit signal")

        # Entries
        if cross > 0 and slope > 0:
            return Signal(side=Side.LONG, confidence=conf, reason="Crossover up with MA slope up")
        if cross < 0 and slope < 0:
            return Signal(side=Side.SHORT, confidence=conf, reason="Crossover down with MA slope down")
        return Signal(side=Side.FLAT, confidence=0.0, reason="No entry signal")

