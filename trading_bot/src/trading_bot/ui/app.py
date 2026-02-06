from __future__ import annotations

from dataclasses import dataclass

from textual.app import App

from trading_bot.core.config import AppConfig
from trading_bot.engine.bot_engine import BotEngine
from trading_bot.engine.state import EngineCommand
from trading_bot.persistence.db import Database
from trading_bot.ui.screens import (
    DashboardScreen,
    DecisionsScreen,
    ResourcesScreen,
    SettingsScreen,
    TradesScreen,
)


class TradingBotApp(App):
    CSS = """
    Screen { padding: 1; }
    #rank_table, #pos_table { height: 16; }
    #events { height: 8; }
    #settings_editor { height: 1fr; }
    """

    BINDINGS = [
        ("1", "dashboard", "Dashboard"),
        ("2", "trades", "Trades"),
        ("3", "decisions", "Decisions"),
        ("4", "settings", "Settings"),
        ("5", "resources", "Resources"),
        ("p", "toggle_pause", "Pause/Resume"),
        ("r", "refresh", "Refresh"),
        ("s", "save_settings", "Save Settings"),
        ("q", "quit_app", "Quit"),
    ]

    SCREENS = {
        "dashboard": DashboardScreen,
        "trades": TradesScreen,
        "decisions": DecisionsScreen,
        "settings": SettingsScreen,
        "resources": ResourcesScreen,
    }

    def __init__(self, *, engine: BotEngine, db: Database, config: AppConfig) -> None:
        super().__init__()
        self.engine = engine
        self.db = db
        self.config = config

    def engine_command(self, kind: str, payload: dict) -> EngineCommand:
        return EngineCommand(kind=kind, payload=payload)

    def on_mount(self) -> None:
        self.engine.start()
        self._go("dashboard")
        refresh_hz = float(self.config.ui.refresh_hz or 2)
        self.set_interval(1.0 / max(refresh_hz, 0.5), self._tick_refresh)

    def _tick_refresh(self) -> None:
        snap = self.engine.get_snapshot()
        screen = self.screen
        if hasattr(screen, "refresh_data"):
            screen.refresh_data(snap)  # type: ignore[attr-defined]

    def action_dashboard(self) -> None:
        self._go("dashboard")

    def action_trades(self) -> None:
        self._go("trades")

    def action_decisions(self) -> None:
        self._go("decisions")

    def action_settings(self) -> None:
        self._go("settings")

    def action_resources(self) -> None:
        self._go("resources")

    def action_toggle_pause(self) -> None:
        snap = self.engine.get_snapshot()
        if snap.paused:
            self.engine.enqueue(self.engine_command("resume", {}))
        else:
            self.engine.enqueue(self.engine_command("pause", {}))

    def action_refresh(self) -> None:
        self._tick_refresh()

    def action_save_settings(self) -> None:
        if isinstance(self.screen, SettingsScreen):
            self.screen.save_settings()

    def action_quit_app(self) -> None:
        self.engine.enqueue(self.engine_command("quit", {}))
        self.engine.request_stop()
        self.exit()

    def on_shutdown_request(self) -> None:  # pragma: no cover
        self.engine.request_stop()

    def _go(self, screen_name: str) -> None:
        try:
            self.switch_screen(screen_name)  # textual>=0.50
        except Exception:
            self.push_screen(screen_name)
