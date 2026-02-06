from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from trading_bot.connectors.base import BrokerConnector
from trading_bot.core.timeframes import timeframe_seconds


@dataclass
class CandleCloseScheduler:
    timeframe: str
    last_candle_close_time_utc: datetime | None = None
    _log: Any = None

    def __post_init__(self) -> None:
        self._log = logging.getLogger("trading_bot.scheduler")

    def poll(self, *, connector: BrokerConnector, anchor_symbol: str) -> datetime | None:
        """
        Returns new candle close time (UTC) if a new candle has closed.
        Uses the anchor symbol's last closed bar as a global clock.
        """
        df = connector.get_candles(anchor_symbol, self.timeframe, 3)
        if df is None or df.empty or len(df) < 3:
            return None
        # df sorted ascending; last row may be forming bar; previous row is last closed bar open time.
        open_time = df["time_utc"].iloc[-2]
        if hasattr(open_time, "to_pydatetime"):
            open_dt = open_time.to_pydatetime()
        else:
            open_dt = open_time
        if getattr(open_dt, "tzinfo", None) is None:
            open_dt = open_dt.replace(tzinfo=timezone.utc)
        close_time = open_dt.astimezone(timezone.utc) + timedelta(
            seconds=timeframe_seconds(self.timeframe)
        )
        if self.last_candle_close_time_utc is None or close_time > self.last_candle_close_time_utc:
            self.last_candle_close_time_utc = close_time
            return close_time
        return None
