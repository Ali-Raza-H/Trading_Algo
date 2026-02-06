from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from trading_bot.connectors.base import (
    AccountInfo,
    AccountTradeMode,
    AssetClass,
    BrokerConnector,
    Deal,
    OrderRequest,
    OrderResult,
    Position,
    Quote,
    Side,
    SymbolMeta,
)
from trading_bot.core.config import AppConfig
from trading_bot.data.pipeline import DataPipeline
from trading_bot.ranking.correlation import greedy_correlation_filter
from trading_bot.ranking.ranker import Ranker


class FakeConnector(BrokerConnector):
    def __init__(self, candles_by_symbol: dict[str, pd.DataFrame], quotes: dict[str, Quote], meta: dict[str, SymbolMeta]) -> None:
        self._candles = candles_by_symbol
        self._quotes = quotes
        self._meta = meta

    def discover_symbols(self) -> list[SymbolMeta]:
        return list(self._meta.values())

    def get_symbol_info(self, symbol: str) -> SymbolMeta | None:
        return self._meta.get(symbol)

    def get_candles(self, symbol: str, timeframe: str, n: int) -> pd.DataFrame:
        return self._candles[symbol].tail(n).copy()

    def get_quote(self, symbol: str) -> Quote | None:
        return self._quotes.get(symbol)

    def list_positions(self) -> list[Position]:
        return []

    def place_order(self, req: OrderRequest) -> OrderResult:
        return OrderResult(success=False, retcode=None, order_ticket=None, position_id=None, comment=None, raw={})

    def modify_position(self, *, position_id: int, sl: float | None, tp: float | None) -> bool:
        return False

    def list_deals(self, from_utc: datetime, to_utc: datetime) -> list[Deal]:
        return []

    def account_info(self) -> AccountInfo | None:
        return None

    def shutdown(self) -> None:
        return None


def _make_candles(seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + rng.standard_normal(400).cumsum()
    df = pd.DataFrame(
        {
            "time": np.arange(len(close)),
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "tick_volume": 100,
            "spread": 10,
            "real_volume": 0,
        }
    )
    df["time_utc"] = pd.to_datetime(np.arange(len(close)), unit="s", utc=True)
    df["time_local"] = df["time_utc"]
    return df


def test_correlation_filter_excludes_high_corr() -> None:
    # Two identical return series -> corr ~ 1
    t = pd.Series(np.linspace(0, 1, 300))
    returns = pd.DataFrame({"A": t, "B": t, "C": -t})
    decision = greedy_correlation_filter(["A", "B", "C"], returns, max_abs_corr=0.85, top_n=2)
    assert "A" in decision.selected
    assert "B" not in decision.selected or "C" not in decision.selected


def test_ranker_returns_top_n() -> None:
    cfg = AppConfig()
    cfg.ranking.top_n = 2
    cfg.ranking.min_bars_required = 200

    meta = {
        "AAA": SymbolMeta(
            name="AAA",
            description=None,
            path=None,
            asset_class=AssetClass.FOREX,
            currency_base=None,
            currency_profit=None,
            currency_margin=None,
            digits=5,
            point=0.00001,
            trade_mode=None,
            trade_allowed=True,
            spread_points=10,
            trade_stops_level=0,
            volume_min=0.01,
            volume_max=1.0,
            volume_step=0.01,
            trade_tick_value=1.0,
            trade_tick_size=0.00001,
            trade_contract_size=100000,
            extra={},
        ),
        "BBB": None,
    }
    meta["BBB"] = meta["AAA"].__class__(**{**meta["AAA"].__dict__, "name": "BBB"})

    candles = {"AAA": _make_candles(1), "BBB": _make_candles(2)}
    now = datetime.now(timezone.utc)
    quotes = {
        "AAA": Quote("AAA", bid=1.0, ask=1.0002, time_utc=now, spread_points=20),
        "BBB": Quote("BBB", bid=1.0, ask=1.0002, time_utc=now, spread_points=20),
    }
    conn = FakeConnector(candles_by_symbol=candles, quotes=quotes, meta={"AAA": meta["AAA"], "BBB": meta["BBB"]})
    pipeline = DataPipeline(conn, timeframe="H1", warmup_bars=300)
    ranker = Ranker(connector=conn, pipeline=pipeline, ranking_config=cfg.ranking, timeframe="H1")
    out = ranker.rank(["AAA", "BBB"], {"AAA": meta["AAA"], "BBB": meta["BBB"]})
    assert len(out.selected) == 2
    assert all(0.0 <= s.score <= 1.0 for s in out.selected)

