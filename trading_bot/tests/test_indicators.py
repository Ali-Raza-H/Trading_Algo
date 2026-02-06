from __future__ import annotations

import numpy as np
import pandas as pd

from trading_bot.indicators.adx import adx
from trading_bot.indicators.atr import atr
from trading_bot.indicators.rsi import rsi
from trading_bot.indicators.two_pole_oscillator import super_smoother_2pole, two_pole_oscillator


def _ohlc_from_close(close: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"close": close})
    df["open"] = close.shift(1).fillna(close)
    df["high"] = close * 1.001
    df["low"] = close * 0.999
    return df[["open", "high", "low", "close"]]


def test_atr_positive_after_warmup() -> None:
    close = pd.Series(np.linspace(100, 110, 200))
    df = _ohlc_from_close(close)
    v = atr(df, period=14)
    assert len(v) == len(df)
    assert float(v.dropna().iloc[-1]) > 0


def test_rsi_bounds() -> None:
    close = pd.Series(np.linspace(100, 110, 200))
    v = rsi(close, period=14).dropna()
    assert v.min() >= 0
    assert v.max() <= 100


def test_adx_non_negative() -> None:
    close = pd.Series(np.linspace(100, 130, 300))
    df = _ohlc_from_close(close)
    out = adx(df, period=14)
    assert set(out.columns) == {"plus_di", "minus_di", "adx"}
    v = out["adx"].dropna()
    assert (v >= 0).all()


def test_two_pole_super_smoother_deterministic() -> None:
    close = pd.Series(np.sin(np.linspace(0, 10, 300)) * 10 + 100)
    s1 = super_smoother_2pole(close, period=20)
    s2 = super_smoother_2pole(close, period=20)
    assert np.allclose(s1.fillna(0).to_numpy(), s2.fillna(0).to_numpy())


def test_two_pole_oscillator_has_cross() -> None:
    close = pd.Series(np.sin(np.linspace(0, 30, 600)) * 5 + 100)
    out = two_pole_oscillator(close, period=20, signal_period=9)
    assert "cross" in out.columns
    # should have at least one crossover
    assert int(out["cross"].abs().sum()) > 0

