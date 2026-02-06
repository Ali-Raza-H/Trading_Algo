from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from trading_bot.core.exceptions import PersistenceError
from trading_bot.persistence.migrations import apply_migrations
from trading_bot.persistence.repos import (
    DecisionRepo,
    ErrorRepo,
    HeartbeatRepo,
    SettingsRepo,
    TradeRepo,
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._connect_new()
            try:
                apply_migrations(conn)
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("PRAGMA synchronous=NORMAL;")
                conn.execute("PRAGMA foreign_keys=ON;")
                conn.commit()
            finally:
                conn.close()
            self._initialized = True

    def _connect_new(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,  # autocommit; we manage transactions explicitly
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def conn(self) -> sqlite3.Connection:
        if not getattr(self._local, "conn", None):
            self._local.conn = self._connect_new()
        return self._local.conn

    def close_thread_connection(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            finally:
                self._local.conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.conn()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        try:
            self.conn().execute(sql, params or [])
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def executemany(self, sql: str, params_seq: Iterable[Sequence[Any]]) -> None:
        try:
            self.conn().executemany(sql, params_seq)
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def query_all(self, sql: str, params: Sequence[Any] | None = None) -> list[sqlite3.Row]:
        try:
            cur = self.conn().execute(sql, params or [])
            return list(cur.fetchall())
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def query_one(self, sql: str, params: Sequence[Any] | None = None) -> sqlite3.Row | None:
        try:
            cur = self.conn().execute(sql, params or [])
            return cur.fetchone()
        except Exception as exc:
            raise PersistenceError(str(exc)) from exc

    def decision_repo(self) -> DecisionRepo:
        return DecisionRepo(self)

    def trade_repo(self) -> TradeRepo:
        return TradeRepo(self)

    def error_repo(self) -> ErrorRepo:
        return ErrorRepo(self)

    def settings_repo(self) -> SettingsRepo:
        return SettingsRepo(self)

    def heartbeat_repo(self) -> HeartbeatRepo:
        return HeartbeatRepo(self)

