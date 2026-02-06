from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from trading_bot.connectors.mt5_connector import MT5Connector


class _FakeMT5(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__()
        self.connected = False
        self.init_kwargs: dict[str, object] | None = None

    def initialize(self, **kwargs: object) -> bool:
        self.init_kwargs = dict(kwargs)
        self.connected = True
        return True

    def shutdown(self) -> None:
        self.connected = False

    def terminal_info(self) -> object | None:
        return object() if self.connected else None

    def account_info(self) -> object | None:
        return object() if self.connected else None

    def last_error(self) -> tuple[int, str]:
        return (1, "Success")


def test_initialize_does_not_pass_none_path(monkeypatch) -> None:
    fake = _FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)

    MT5Connector(login=1, password="pw", server="srv", timezone=ZoneInfo("UTC"), path=None)
    assert fake.init_kwargs is not None
    assert "path" not in fake.init_kwargs


def test_initialize_resolves_directory_path(monkeypatch, tmp_path: Path) -> None:
    fake = _FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)

    terminal = tmp_path / "terminal64.exe"
    terminal.write_text("x", encoding="utf-8")

    MT5Connector(login=1, password="pw", server="srv", timezone=ZoneInfo("UTC"), path=str(tmp_path))
    assert fake.init_kwargs is not None
    assert str(terminal) == fake.init_kwargs.get("path")

