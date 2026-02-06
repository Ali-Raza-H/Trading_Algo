from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DecisionRow:
    id: int
    created_at: str
    cycle_id: str
    symbol: str
    timeframe: str
    candle_close_time_utc: str
    rank_score: float | None
    rank_components_json: str | None
    strategy: str | None
    features_json: str | None
    signal_json: str | None
    risk_json: str | None
    order_json: str | None
    result_json: str | None
    status: str
    idempotency_key: str


@dataclass(frozen=True)
class TradeRow:
    id: int
    deal_ticket: int
    position_id: int | None
    order_ticket: int | None
    time_utc: str
    symbol: str
    side: str
    entry: str
    volume: float
    price: float
    profit: float | None
    commission: float | None
    swap: float | None
    magic: int | None
    comment: str | None
    raw_json: str | None


@dataclass(frozen=True)
class ErrorRow:
    id: int
    created_at: str
    cycle_id: str | None
    severity: str
    message: str
    traceback: str | None
    context_json: str | None


@dataclass(frozen=True)
class SettingsSnapshotRow:
    id: int
    created_at: str
    source: str
    config_json: str


@dataclass(frozen=True)
class HeartbeatRow:
    id: int
    created_at: str
    cycle_id: str
    status: str
    cycle_latency_ms: float | None
    mt5_connected: int | None
    equity: float | None
    balance: float | None
    daily_start_equity: float | None
    daily_pnl: float | None
    peak_equity: float | None
    drawdown_pct: float | None
    open_positions: int | None
    cpu_pct: float | None
    ram_pct: float | None
    disk_pct: float | None
    net_rx_bps: float | None
    net_tx_bps: float | None
    temp_c: float | None
    extra_json: str | None


RowT = DecisionRow | TradeRow | ErrorRow | SettingsSnapshotRow | HeartbeatRow
JsonObject = dict[str, Any]

