from __future__ import annotations

import queue
from dataclasses import dataclass, field
from typing import Any

from trading_bot.connectors.base import Side


@dataclass(frozen=True)
class RankedSymbolView:
    symbol: str
    score: float
    components: dict[str, float]
    reasons: list[str]


@dataclass(frozen=True)
class PositionView:
    symbol: str
    side: str
    volume: float
    price_open: float
    sl: float | None
    tp: float | None
    profit: float | None


@dataclass
class EngineSnapshot:
    connected: bool = False
    paused: bool = False
    trading_enabled: bool = False
    last_cycle_id: str | None = None
    last_candle_close_time_utc: str | None = None
    last_cycle_latency_ms: float | None = None
    stage_timings_ms: dict[str, float] = field(default_factory=dict)

    top_ranked: list[RankedSymbolView] = field(default_factory=list)
    open_positions: list[PositionView] = field(default_factory=list)

    today_pnl: float | None = None
    wins: int = 0
    losses: int = 0

    last_events: list[str] = field(default_factory=list)
    last_errors: list[str] = field(default_factory=list)

    resources: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EngineCommand:
    kind: str  # pause | resume | apply_config | refresh_universe | quit
    payload: dict[str, Any] = field(default_factory=dict)


class CommandQueue:
    def __init__(self) -> None:
        self._q: "queue.Queue[EngineCommand]" = queue.Queue()

    def put(self, cmd: EngineCommand) -> None:
        self._q.put(cmd)

    def get_nowait(self) -> EngineCommand | None:
        try:
            return self._q.get_nowait()
        except queue.Empty:
            return None

