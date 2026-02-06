from __future__ import annotations

import math

import numpy as np
import pandas as pd

from trading_bot.indicators.moving_averages import ema


def super_smoother_2pole(series: pd.Series, period: int) -> pd.Series:
    """
    Ehlers 2-pole Super Smoother filter.

    Deterministic recursive form:
      a1 = exp(-1.414 * pi / period)
      b1 = 2 * a1 * cos(1.414 * pi / period)
      c2 = b1
      c3 = -a1^2
      c1 = 1 - c2 - c3
      y[t] = c1*(x[t] + x[t-1])/2 + c2*y[t-1] + c3*y[t-2]
    """
    if period <= 2:
        raise ValueError("period must be > 2 for 2-pole filter")
    if series.empty:
        return pd.Series(dtype="float64")

    a1 = math.exp(-1.414 * math.pi / float(period))
    b1 = 2.0 * a1 * math.cos(1.414 * math.pi / float(period))
    c2 = b1
    c3 = -(a1**2)
    c1 = 1.0 - c2 - c3

    x = series.astype("float64").to_numpy()
    y = np.full_like(x, fill_value=np.nan, dtype=float)
    # seed using first values
    if len(x) >= 1:
        y[0] = x[0]
    if len(x) >= 2:
        y[1] = x[1]
    for i in range(2, len(x)):
        y[i] = (
            c1 * (x[i] + x[i - 1]) / 2.0
            + c2 * y[i - 1]
            + c3 * y[i - 2]
        )
    return pd.Series(y, index=series.index, name="ss2")


def two_pole_oscillator(
    close: pd.Series, period: int = 20, signal_period: int = 9
) -> pd.DataFrame:
    """
    Two-pole momentum oscillator:
      smooth = SS2(close, period)
      osc = close - smooth
      signal = EMA(osc, signal_period)

    Returns columns: smooth, osc, signal, hist, cross
    cross: +1 on osc crossing above signal, -1 on crossing below, 0 otherwise.
    """
    smooth = super_smoother_2pole(close, period=period)
    osc = (close.astype("float64") - smooth).rename("osc")
    sig = ema(osc, period=signal_period).rename("signal")
    hist = (osc - sig).rename("hist")
    prev = hist.shift(1)
    cross_up = (prev <= 0) & (hist > 0)
    cross_dn = (prev >= 0) & (hist < 0)
    cross = pd.Series(0, index=close.index, dtype="int64")
    cross[cross_up] = 1
    cross[cross_dn] = -1
    return pd.DataFrame(
        {
            "smooth": smooth,
            "osc": osc,
            "signal": sig,
            "hist": hist,
            "cross": cross,
        }
    )

