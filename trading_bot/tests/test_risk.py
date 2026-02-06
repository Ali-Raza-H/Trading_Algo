from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trading_bot.connectors.base import (
    AccountInfo,
    AccountTradeMode,
    AssetClass,
    Position,
    Quote,
    Side,
    SymbolMeta,
)
from trading_bot.core.config import AppConfig
from trading_bot.persistence.db import Database
from trading_bot.risk.risk_manager import RiskManager


def _symbol_meta() -> SymbolMeta:
    return SymbolMeta(
        name="EURUSD",
        description=None,
        path=None,
        asset_class=AssetClass.FOREX,
        currency_base="EUR",
        currency_profit="USD",
        currency_margin="USD",
        digits=5,
        point=0.00001,
        trade_mode=None,
        trade_allowed=True,
        spread_points=10,
        trade_stops_level=0,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        trade_tick_value=1.0,
        trade_tick_size=0.00001,
        trade_contract_size=100000,
        extra={},
    )


def test_risk_pauses_on_daily_loss(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.persistence.db_path = str(tmp_path / "bot.sqlite")
    db = Database(Path(cfg.persistence.db_path))
    db.initialize()
    rm = RiskManager(cfg, db=db)

    eq1 = AccountInfo(
        login=1,
        server="demo",
        currency="USD",
        leverage=100,
        balance=1000.0,
        equity=1000.0,
        margin=0.0,
        trade_mode=AccountTradeMode.DEMO,
        name=None,
        company=None,
        raw={},
    )
    state = rm.update_equity_state(account=eq1, now_local_date="2026-01-01")
    assert state["paused"] is False

    eq2 = eq1.__class__(**{**eq1.__dict__, "equity": 1000.0 * (1 - cfg.risk.max_daily_loss_pct - 0.01)})
    state2 = rm.update_equity_state(account=eq2, now_local_date="2026-01-01")
    assert state2["paused"] is True


def test_entry_blocked_when_max_positions(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.persistence.db_path = str(tmp_path / "bot.sqlite")
    cfg.risk.max_open_positions_total = 1
    db = Database(Path(cfg.persistence.db_path))
    db.initialize()
    rm = RiskManager(cfg, db=db)

    account = AccountInfo(
        login=1,
        server="demo",
        currency="USD",
        leverage=100,
        balance=1000.0,
        equity=1000.0,
        margin=0.0,
        trade_mode=AccountTradeMode.DEMO,
        name=None,
        company=None,
        raw={},
    )
    rm.update_equity_state(account=account, now_local_date="2026-01-01")

    q = Quote("EURUSD", bid=1.0, ask=1.0002, time_utc=datetime.now(timezone.utc), spread_points=20)
    meta = _symbol_meta()
    feats = {"atr14": 0.001, "close": 1.0}
    pos = Position(
        position_id=1,
        symbol="EURUSD",
        side=Side.LONG,
        volume=0.01,
        price_open=1.0,
        sl=None,
        tp=None,
        time_utc=datetime.now(timezone.utc),
        profit=None,
        swap=None,
        commission=None,
        magic=cfg.execution.magic_number,
        comment=None,
        raw={},
    )
    dec = rm.check_entry(symbol="EURUSD", side=Side.LONG, quote=q, symbol_meta=meta, features=feats, positions=[pos], account=account)
    assert dec.allowed is False

