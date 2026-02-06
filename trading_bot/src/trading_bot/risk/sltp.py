from __future__ import annotations

from dataclasses import dataclass

from trading_bot.connectors.base import Side


@dataclass(frozen=True)
class SLTP:
    sl: float | None
    tp: float | None
    stop_points: float | None
    take_points: float | None


def sltp_rr(*, side: Side, entry: float, point: float, stop_points: int, take_points: int) -> SLTP:
    if point <= 0:
        return SLTP(sl=None, tp=None, stop_points=None, take_points=None)
    if side == Side.LONG:
        sl = entry - float(stop_points) * point
        tp = entry + float(take_points) * point
    else:
        sl = entry + float(stop_points) * point
        tp = entry - float(take_points) * point
    return SLTP(sl=sl, tp=tp, stop_points=float(stop_points), take_points=float(take_points))


def sltp_atr(*, side: Side, entry: float, atr: float, sl_mult: float, tp_mult: float) -> SLTP:
    if atr <= 0:
        return SLTP(sl=None, tp=None, stop_points=None, take_points=None)
    sl_dist = float(atr) * float(sl_mult)
    tp_dist = float(atr) * float(tp_mult)
    if side == Side.LONG:
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:
        sl = entry + sl_dist
        tp = entry - tp_dist
    return SLTP(sl=sl, tp=tp, stop_points=None, take_points=None)

