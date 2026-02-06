from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.indicators.atr import rma


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI (Wilder).
    Returns 0..100.
    """
    if period <= 0:
        raise ValueError("period must be > 0")
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_val = 100.0 - (100.0 / (1.0 + rs))

    eps = 1e-12
    both_zero = (avg_gain.abs() <= eps) & (avg_loss.abs() <= eps)
    loss_zero = (avg_loss.abs() <= eps) & ~both_zero
    gain_zero = (avg_gain.abs() <= eps) & ~both_zero
    rsi_val = rsi_val.where(~loss_zero, 100.0)
    rsi_val = rsi_val.where(~gain_zero, 0.0)
    rsi_val = rsi_val.where(~both_zero, 50.0)

    return rsi_val.astype("float64")
