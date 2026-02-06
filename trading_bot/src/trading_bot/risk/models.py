from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from trading_bot.connectors.base import Side


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    side: Side
    volume: float | None = None
    sl: float | None = None
    tp: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskState:
    paused: bool = False
    pause_reason: str | None = None
    cooloff_until_utc: datetime | None = None
    loss_streak: int = 0

    # Equity tracking
    daily_date: str | None = None  # YYYY-MM-DD in runtime timezone
    daily_start_equity: float | None = None
    peak_equity: float | None = None

