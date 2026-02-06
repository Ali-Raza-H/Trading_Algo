from __future__ import annotations

import numpy as np
import pandas as pd


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = (high - low).abs()
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def rma(series: pd.Series, period: int) -> pd.Series:
    # Wilder's smoothing (RMA) is equivalent to EMA with alpha=1/period.
    if period <= 0:
        raise ValueError("period must be > 0")
    alpha = 1.0 / float(period)
    return series.ewm(alpha=alpha, adjust=False, min_periods=period).mean()


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Average True Range (Wilder).

    Expects columns: high, low, close
    Returns ATR in price units.
    """
    if df.empty:
        return pd.Series(dtype="float64")
    tr = true_range(df["high"], df["low"], df["close"])
    return rma(tr, period)

