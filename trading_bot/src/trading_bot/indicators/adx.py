from __future__ import annotations

import pandas as pd

from trading_bot.indicators.atr import rma, true_range


def adx(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    ADX (+DI/-DI) (Wilder).

    Expects columns: high, low, close
    Returns DataFrame with columns: plus_di, minus_di, adx
    """
    if df.empty:
        return pd.DataFrame({"plus_di": [], "minus_di": [], "adx": []})

    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr = true_range(high, low, close)
    atr_val = rma(tr, period)

    plus_di = 100.0 * (rma(plus_dm, period) / atr_val.replace(0.0, pd.NA))
    minus_di = 100.0 * (rma(minus_dm, period) / atr_val.replace(0.0, pd.NA))

    dx = (100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, pd.NA)).astype(
        "float64"
    )
    adx_val = rma(dx, period)

    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": adx_val})

