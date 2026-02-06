from __future__ import annotations

import pandas as pd


REQUIRED_COLUMNS = {"open", "high", "low", "close"}


def validate_candles(df: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"candles missing columns: {sorted(missing)}")
    if "time_utc" not in df.columns:
        raise ValueError("candles missing time_utc column")


def closes(df: pd.DataFrame) -> pd.Series:
    validate_candles(df)
    return df["close"].astype("float64")


def returns(df: pd.DataFrame) -> pd.Series:
    c = closes(df)
    return c.pct_change().astype("float64")

