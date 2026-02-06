from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable

from trading_bot.core.utils import safe_json_dumps


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionRepo:
    def __init__(self, db: "Database") -> None:
        self.db = db

    def try_insert(
        self,
        *,
        cycle_id: str,
        symbol: str,
        timeframe: str,
        candle_close_time_utc: str,
        rank_score: float | None,
        rank_components: dict[str, Any] | None,
        strategy: str | None,
        features: dict[str, Any] | None,
        signal: dict[str, Any] | None,
        risk: dict[str, Any] | None,
        order: dict[str, Any] | None,
        result: dict[str, Any] | None,
        status: str,
        idempotency_key: str,
    ) -> bool:
        sql = """
        INSERT INTO decisions(
          created_at, cycle_id, symbol, timeframe, candle_close_time_utc,
          rank_score, rank_components_json, strategy, features_json, signal_json,
          risk_json, order_json, result_json, status, idempotency_key
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        params = (
            _utc_iso(),
            cycle_id,
            symbol,
            timeframe,
            candle_close_time_utc,
            rank_score,
            safe_json_dumps(rank_components) if rank_components is not None else None,
            strategy,
            safe_json_dumps(features) if features is not None else None,
            safe_json_dumps(signal) if signal is not None else None,
            safe_json_dumps(risk) if risk is not None else None,
            safe_json_dumps(order) if order is not None else None,
            safe_json_dumps(result) if result is not None else None,
            status,
            idempotency_key,
        )
        try:
            self.db.conn().execute(sql, params)
            return True
        except sqlite3.IntegrityError:
            return False

    def list_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]


class TradeRepo:
    def __init__(self, db: "Database") -> None:
        self.db = db

    def insert_deals(self, deals: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        sql = """
        INSERT OR IGNORE INTO trades(
          deal_ticket, position_id, order_ticket, time_utc, symbol, side, entry,
          volume, price, profit, commission, swap, magic, comment, raw_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        inserted: list[dict[str, Any]] = []
        cur = self.db.conn().cursor()
        for d in deals:
            cur.execute(
                sql,
                (
                    int(d["deal_ticket"]),
                    d.get("position_id"),
                    d.get("order_ticket"),
                    d["time_utc"],
                    d["symbol"],
                    d["side"],
                    d["entry"],
                    float(d["volume"]),
                    float(d["price"]),
                    d.get("profit"),
                    d.get("commission"),
                    d.get("swap"),
                    d.get("magic"),
                    d.get("comment"),
                    safe_json_dumps(d.get("raw")) if d.get("raw") is not None else None,
                ),
            )
            if cur.rowcount:
                inserted.append(d)
        return inserted

    def list_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self.db.query_all(
            "SELECT * FROM trades ORDER BY time_utc DESC, id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]


class ErrorRepo:
    def __init__(self, db: "Database") -> None:
        self.db = db

    def insert(
        self,
        *,
        severity: str,
        message: str,
        traceback: str | None,
        cycle_id: str | None,
        context: dict[str, Any] | None,
    ) -> None:
        self.db.conn().execute(
            """
            INSERT INTO errors(created_at, cycle_id, severity, message, traceback, context_json)
            VALUES(?,?,?,?,?,?)
            """,
            (
                _utc_iso(),
                cycle_id,
                severity,
                message,
                traceback,
                safe_json_dumps(context) if context else None,
            ),
        )

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.db.query_all("SELECT * FROM errors ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]


class SettingsRepo:
    def __init__(self, db: "Database") -> None:
        self.db = db

    def insert_snapshot(self, *, source: str, config: dict[str, Any]) -> None:
        self.db.conn().execute(
            """
            INSERT INTO settings_snapshots(created_at, source, config_json)
            VALUES(?,?,?)
            """,
            (_utc_iso(), source, safe_json_dumps(config)),
        )

    def get_latest_snapshot_json(self) -> str | None:
        row = self.db.query_one(
            "SELECT config_json FROM settings_snapshots ORDER BY id DESC LIMIT 1"
        )
        return str(row["config_json"]) if row else None


class HeartbeatRepo:
    def __init__(self, db: "Database") -> None:
        self.db = db

    def insert(self, payload: dict[str, Any]) -> None:
        self.db.conn().execute(
            """
            INSERT INTO heartbeats(
              created_at, cycle_id, status, cycle_latency_ms, mt5_connected, equity, balance,
              daily_start_equity, daily_pnl, peak_equity, drawdown_pct, open_positions,
              cpu_pct, ram_pct, disk_pct, net_rx_bps, net_tx_bps, temp_c, extra_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                payload.get("created_at") or _utc_iso(),
                payload["cycle_id"],
                payload.get("status") or "ok",
                payload.get("cycle_latency_ms"),
                payload.get("mt5_connected"),
                payload.get("equity"),
                payload.get("balance"),
                payload.get("daily_start_equity"),
                payload.get("daily_pnl"),
                payload.get("peak_equity"),
                payload.get("drawdown_pct"),
                payload.get("open_positions"),
                payload.get("cpu_pct"),
                payload.get("ram_pct"),
                payload.get("disk_pct"),
                payload.get("net_rx_bps"),
                payload.get("net_tx_bps"),
                payload.get("temp_c"),
                safe_json_dumps(payload.get("extra")) if payload.get("extra") else None,
            ),
        )

    def latest(self) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM heartbeats ORDER BY id DESC LIMIT 1")
        return dict(row) if row else None
if TYPE_CHECKING:  # pragma: no cover
    from trading_bot.persistence.db import Database
