from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from trading_bot.indicators.adx import adx as adx_ind
from trading_bot.indicators.atr import atr as atr_ind
from trading_bot.indicators.moving_averages import ema
from trading_bot.indicators.rsi import rsi as rsi_ind
from trading_bot.indicators.two_pole_oscillator import two_pole_oscillator


def compute_features(df: pd.DataFrame) -> dict[str, Any]:
    """
    Compute a consistent feature set from OHLC candles.

    Input: DataFrame sorted ascending with columns: time_utc, open, high, low, close
    Output: dict with latest values and small lookback stats.
    """
    if df is None or df.empty:
        return {}
    close = df["close"].astype("float64")

    atr14 = atr_ind(df, period=14)
    adx14 = adx_ind(df, period=14)
    rsi14 = rsi_ind(close, period=14)
    ema50 = ema(close, period=50)
    ema50_slope = ema50.diff()
    osc = two_pole_oscillator(close, period=20, signal_period=9)

    last = len(df) - 1
    out: dict[str, Any] = {
        "close": float(close.iloc[last]),
        "atr14": float(atr14.iloc[last]) if not np.isnan(atr14.iloc[last]) else None,
        "atr14_pct": float(atr14.iloc[last] / close.iloc[last]) if close.iloc[last] else None,
        "adx14": float(adx14["adx"].iloc[last]) if not np.isnan(adx14["adx"].iloc[last]) else None,
        "plus_di14": float(adx14["plus_di"].iloc[last]) if not np.isnan(adx14["plus_di"].iloc[last]) else None,
        "minus_di14": float(adx14["minus_di"].iloc[last]) if not np.isnan(adx14["minus_di"].iloc[last]) else None,
        "rsi14": float(rsi14.iloc[last]) if not np.isnan(rsi14.iloc[last]) else None,
        "ema50": float(ema50.iloc[last]) if not np.isnan(ema50.iloc[last]) else None,
        "ema50_slope": float(ema50_slope.iloc[last]) if not np.isnan(ema50_slope.iloc[last]) else None,
        "tp_osc": float(osc["osc"].iloc[last]) if not np.isnan(osc["osc"].iloc[last]) else None,
        "tp_signal": float(osc["signal"].iloc[last]) if not np.isnan(osc["signal"].iloc[last]) else None,
        "tp_hist": float(osc["hist"].iloc[last]) if not np.isnan(osc["hist"].iloc[last]) else None,
        "tp_cross": int(osc["cross"].iloc[last]) if not np.isnan(osc["cross"].iloc[last]) else 0,
    }

    # Basic recent return momentum (fallback)
    ret_20 = close.pct_change(20)
    out["ret20"] = float(ret_20.iloc[last]) if not np.isnan(ret_20.iloc[last]) else None
    return out

