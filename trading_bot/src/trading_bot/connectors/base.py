from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Iterable

import pandas as pd


class AssetClass(str, Enum):
    FOREX = "forex"
    METALS = "metals"
    INDICES = "indices"
    STOCKS = "stocks"
    UNKNOWN = "unknown"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class AccountTradeMode(str, Enum):
    DEMO = "DEMO"
    REAL = "REAL"
    CONTEST = "CONTEST"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SymbolMeta:
    name: str
    description: str | None
    path: str | None
    asset_class: AssetClass
    currency_base: str | None
    currency_profit: str | None
    currency_margin: str | None
    digits: int | None
    point: float | None
    trade_mode: int | None
    trade_allowed: bool | None
    spread_points: float | None
    trade_stops_level: int | None
    volume_min: float | None
    volume_max: float | None
    volume_step: float | None
    trade_tick_value: float | None
    trade_tick_size: float | None
    trade_contract_size: float | None
    extra: dict[str, Any]


@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    time_utc: datetime
    spread_points: float


@dataclass(frozen=True)
class Position:
    position_id: int
    symbol: str
    side: Side
    volume: float
    price_open: float
    sl: float | None
    tp: float | None
    time_utc: datetime
    profit: float | None
    swap: float | None
    commission: float | None
    magic: int | None
    comment: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class Deal:
    deal_ticket: int
    position_id: int | None
    order_ticket: int | None
    time_utc: datetime
    symbol: str
    side: Side
    entry: str
    volume: float
    price: float
    profit: float | None
    commission: float | None
    swap: float | None
    magic: int | None
    comment: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class AccountInfo:
    login: int | None
    server: str | None
    currency: str | None
    leverage: int | None
    balance: float | None
    equity: float | None
    margin: float | None
    trade_mode: AccountTradeMode
    name: str | None
    company: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    volume: float
    sl: float | None
    tp: float | None
    deviation_points: int
    magic: int
    comment: str
    idempotency_key: str
    position_id: int | None = None  # if set, request is intended to close that position


@dataclass(frozen=True)
class OrderResult:
    success: bool
    retcode: int | None
    order_ticket: int | None
    position_id: int | None
    comment: str | None
    raw: dict[str, Any]


class BrokerConnector(ABC):
    @abstractmethod
    def discover_symbols(self) -> list[SymbolMeta]:
        raise NotImplementedError

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> SymbolMeta | None:
        raise NotImplementedError

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, n: int) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote | None:
        raise NotImplementedError

    @abstractmethod
    def list_positions(self) -> list[Position]:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, req: OrderRequest) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    def modify_position(self, *, position_id: int, sl: float | None, tp: float | None) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_deals(self, from_utc: datetime, to_utc: datetime) -> list[Deal]:
        raise NotImplementedError

    @abstractmethod
    def account_info(self) -> AccountInfo | None:
        raise NotImplementedError

    @abstractmethod
    def shutdown(self) -> None:
        raise NotImplementedError

