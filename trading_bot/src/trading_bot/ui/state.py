from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.core.config import AppConfig
from trading_bot.engine.state import EngineSnapshot
from trading_bot.persistence.db import Database
from trading_bot.engine.bot_engine import BotEngine


@dataclass
class UIContext:
    engine: BotEngine
    db: Database
    config: AppConfig
    snapshot: EngineSnapshot | None = None
    last_error: str | None = None

