from __future__ import annotations

import math
from dataclasses import dataclass

from trading_bot.connectors.base import SymbolMeta


@dataclass(frozen=True)
class VolumeResult:
    ok: bool
    volume: float | None
    reason: str


def _round_down_to_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor(value / step) * step


def compute_volume(
    *,
    equity: float,
    risk_per_trade: float,
    stop_points: float,
    symbol: SymbolMeta,
) -> VolumeResult:
    """
    Risk-based sizing using MT5 tick_value/tick_size/point.

    money_per_point_per_lot = tick_value * point / tick_size
    volume_lots = (equity * risk_per_trade) / (stop_points * money_per_point_per_lot)
    """
    if equity <= 0:
        return VolumeResult(ok=False, volume=None, reason="equity unavailable")
    if stop_points <= 0:
        return VolumeResult(ok=False, volume=None, reason="invalid stop distance")
    point = float(symbol.point or 0.0)
    tick_value = float(symbol.trade_tick_value or 0.0)
    tick_size = float(symbol.trade_tick_size or 0.0)
    if point <= 0 or tick_value <= 0 or tick_size <= 0:
        return VolumeResult(ok=False, volume=None, reason="missing symbol tick metadata for sizing")

    money_per_point = tick_value * point / tick_size
    if money_per_point <= 0:
        return VolumeResult(ok=False, volume=None, reason="invalid tick metadata")

    risk_money = float(equity) * float(risk_per_trade)
    vol = risk_money / (float(stop_points) * money_per_point)

    vol_min = float(symbol.volume_min or 0.0)
    vol_max = float(symbol.volume_max or 0.0) if symbol.volume_max else None
    vol_step = float(symbol.volume_step or 0.0)

    if vol_min > 0:
        vol = max(vol, vol_min)
    if vol_max and vol_max > 0:
        vol = min(vol, vol_max)
    if vol_step > 0:
        vol = _round_down_to_step(vol, vol_step)
        if vol_min > 0 and vol < vol_min:
            vol = vol_min

    if vol <= 0:
        return VolumeResult(ok=False, volume=None, reason="computed volume <= 0")
    return VolumeResult(ok=True, volume=float(vol), reason="risk sized")
