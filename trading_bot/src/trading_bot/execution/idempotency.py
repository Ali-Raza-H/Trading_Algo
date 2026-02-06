from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from trading_bot.core.utils import sha256_hex


def make_idempotency_key(
    *,
    symbol: str,
    timeframe: str,
    candle_close_time_utc: str,
    strategy: str,
    side: str,
) -> str:
    raw = f"{symbol}|{timeframe}|{candle_close_time_utc}|{strategy}|{side}"
    return sha256_hex(raw)


@dataclass
class IdempotencyCache:
    seen: set[str] = field(default_factory=set)
    _log: Any = field(default_factory=lambda: logging.getLogger("trading_bot.idempotency"))

    def load_recent(self, *, db: Any, limit: int = 5000) -> None:
        try:
            rows = db.query_all(
                "SELECT idempotency_key FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
            )
        except Exception:
            return
        for r in rows:
            k = r["idempotency_key"]
            if k:
                self.seen.add(str(k))
        self._log.info("idempotency cache loaded", extra={"keys": len(self.seen)})

    def contains(self, key: str) -> bool:
        return key in self.seen

    def add(self, key: str) -> None:
        self.seen.add(key)

