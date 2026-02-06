from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    if period <= 0:
        raise ValueError("period must be > 0")
    return series.ewm(span=period, adjust=False, min_periods=period).mean()

