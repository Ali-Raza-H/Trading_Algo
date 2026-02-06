from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import requests

from trading_bot.notifications.throttle import Throttle


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool
    token: str | None
    chat_ids: list[str]
    throttle_seconds: float


class TelegramNotifier:
    def __init__(self, cfg: TelegramConfig) -> None:
        self.cfg = cfg
        self._log = logging.getLogger("trading_bot.telegram")
        self._throttle = Throttle(throttle_seconds=float(cfg.throttle_seconds))

    @classmethod
    def from_env(cls, *, enabled: bool, throttle_seconds: float) -> "TelegramNotifier":
        token = os.getenv("TELEGRAM_BOT_TOKEN") or None
        ids = []
        for k in ("TELEGRAM_CHAT_ID_USER", "TELEGRAM_CHAT_ID_DAD"):
            v = os.getenv(k)
            if v:
                ids.append(v.strip())
        cfg = TelegramConfig(enabled=bool(enabled), token=token, chat_ids=ids, throttle_seconds=float(throttle_seconds))
        return cls(cfg)

    def available(self) -> bool:
        return bool(self.cfg.enabled and self.cfg.token and self.cfg.chat_ids)

    def send(self, message: str, *, key: str | None = None) -> None:
        if not self.cfg.enabled:
            return
        if not self.cfg.token or not self.cfg.chat_ids:
            return
        if key and not self._throttle.allow(key):
            return
        for chat_id in self.cfg.chat_ids:
            self._send_one(chat_id, message)

    def _send_one(self, chat_id: str, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.cfg.token}/sendMessage"
        try:
            r = requests.post(
                url,
                json={"chat_id": chat_id, "text": message},
                timeout=5,
            )
            if r.status_code >= 400:
                self._log.warning(
                    "telegram send failed",
                    extra={"status": r.status_code, "body": r.text[:200]},
                )
        except Exception as exc:
            self._log.warning("telegram exception", extra={"error": str(exc)})

