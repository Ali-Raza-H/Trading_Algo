from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


LATEST_VERSION = 1


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations(
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        )
        """
    )


def current_version(conn: sqlite3.Connection) -> int:
    ensure_migrations_table(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    if row is None:
        return 0
    v = row[0]
    return int(v) if v is not None else 0


def apply_migrations(conn: sqlite3.Connection) -> None:
    ensure_migrations_table(conn)
    v = current_version(conn)
    if v < 1:
        _migration_v1(conn)
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES(?,?)",
            (1, _utc_iso()),
        )
        conn.commit()


def _migration_v1(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS decisions(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          cycle_id TEXT NOT NULL,
          symbol TEXT NOT NULL,
          timeframe TEXT NOT NULL,
          candle_close_time_utc TEXT NOT NULL,
          rank_score REAL,
          rank_components_json TEXT,
          strategy TEXT,
          features_json TEXT,
          signal_json TEXT,
          risk_json TEXT,
          order_json TEXT,
          result_json TEXT,
          status TEXT NOT NULL,
          idempotency_key TEXT NOT NULL UNIQUE
        );
        CREATE INDEX IF NOT EXISTS idx_decisions_created_at ON decisions(created_at);
        CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
        CREATE INDEX IF NOT EXISTS idx_decisions_cycle ON decisions(cycle_id);

        CREATE TABLE IF NOT EXISTS trades(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          deal_ticket INTEGER NOT NULL UNIQUE,
          position_id INTEGER,
          order_ticket INTEGER,
          time_utc TEXT NOT NULL,
          symbol TEXT NOT NULL,
          side TEXT NOT NULL,
          entry TEXT NOT NULL,
          volume REAL NOT NULL,
          price REAL NOT NULL,
          profit REAL,
          commission REAL,
          swap REAL,
          magic INTEGER,
          comment TEXT,
          raw_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_trades_time_utc ON trades(time_utc);
        CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);

        CREATE TABLE IF NOT EXISTS errors(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          cycle_id TEXT,
          severity TEXT NOT NULL,
          message TEXT NOT NULL,
          traceback TEXT,
          context_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_errors_created_at ON errors(created_at);

        CREATE TABLE IF NOT EXISTS settings_snapshots(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          source TEXT NOT NULL,
          config_json TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_settings_created_at ON settings_snapshots(created_at);

        CREATE TABLE IF NOT EXISTS heartbeats(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          created_at TEXT NOT NULL,
          cycle_id TEXT NOT NULL,
          status TEXT NOT NULL,
          cycle_latency_ms REAL,
          mt5_connected INTEGER,
          equity REAL,
          balance REAL,
          daily_start_equity REAL,
          daily_pnl REAL,
          peak_equity REAL,
          drawdown_pct REAL,
          open_positions INTEGER,
          cpu_pct REAL,
          ram_pct REAL,
          disk_pct REAL,
          net_rx_bps REAL,
          net_tx_bps REAL,
          temp_c REAL,
          extra_json TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_heartbeats_created_at ON heartbeats(created_at);
        """
    )

