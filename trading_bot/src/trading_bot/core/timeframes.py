from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TimeframeSpec:
    code: str
    seconds: int


TIMEFRAMES: dict[str, TimeframeSpec] = {
    "M1": TimeframeSpec("M1", 60),
    "M5": TimeframeSpec("M5", 5 * 60),
    "M15": TimeframeSpec("M15", 15 * 60),
    "M30": TimeframeSpec("M30", 30 * 60),
    "H1": TimeframeSpec("H1", 60 * 60),
    "H4": TimeframeSpec("H4", 4 * 60 * 60),
    "D1": TimeframeSpec("D1", 24 * 60 * 60),
}


def timeframe_seconds(code: str) -> int:
    if code not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {code}")
    return TIMEFRAMES[code].seconds


def timeframe_to_mt5(code: str) -> int:
    """
    Map timeframe code to MetaTrader5 TIMEFRAME_* constant.

    Import is done lazily so the project can be imported on Linux even when
    MetaTrader5 is unavailable (use Wine/Windows Python for MT5 runtime).
    """
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "MetaTrader5 package is required for MT5Connector. "
            "On Linux, run under Wine with Windows Python."
        ) from exc

    mapping = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "M30": mt5.TIMEFRAME_M30,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    if code not in mapping:
        raise ValueError(f"Unsupported timeframe: {code}")
    return mapping[code]

