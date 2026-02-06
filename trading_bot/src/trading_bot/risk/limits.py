from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from trading_bot.connectors.base import Position


@dataclass(frozen=True)
class PositionCounts:
    total: int
    per_symbol: dict[str, int]


def count_positions(positions: Iterable[Position], *, magic: int | None = None) -> PositionCounts:
    total = 0
    per_symbol: dict[str, int] = {}
    for p in positions:
        if magic is not None and p.magic is not None and int(p.magic) != int(magic):
            continue
        total += 1
        per_symbol[p.symbol] = per_symbol.get(p.symbol, 0) + 1
    return PositionCounts(total=total, per_symbol=per_symbol)


def drawdown_pct(*, peak_equity: float, equity: float) -> float:
    if peak_equity <= 0:
        return 0.0
    return max(0.0, (peak_equity - equity) / peak_equity)


def daily_loss_pct(*, daily_start_equity: float, equity: float) -> float:
    if daily_start_equity <= 0:
        return 0.0
    return max(0.0, (daily_start_equity - equity) / daily_start_equity)

