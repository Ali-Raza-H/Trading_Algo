from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from trading_bot.connectors.base import (
    AccountInfo,
    AccountTradeMode,
    BrokerConnector,
    Deal,
    Position,
    Side,
    SymbolMeta,
)
from trading_bot.connectors.mt5_connector import MT5Connector
from trading_bot.core.config import AppConfig
from trading_bot.core.constants import (
    DECISION_STATUS_NO_SIGNAL,
    DECISION_STATUS_RISK_BLOCKED,
    DECISION_STATUS_SKIPPED,
)
from trading_bot.core.utils import iso_utc, monotonic_ms
from trading_bot.data.pipeline import DataPipeline
from trading_bot.engine.scheduler import CandleCloseScheduler
from trading_bot.engine.state import (
    EngineCommand,
    EngineSnapshot,
    PositionView,
    RankedSymbolView,
)
from trading_bot.execution.executor import TradeExecutor
from trading_bot.execution.idempotency import IdempotencyCache, make_idempotency_key
from trading_bot.monitoring.network import NetworkMonitor
from trading_bot.monitoring.resources import ResourceMonitor
from trading_bot.monitoring.temperatures import best_temperature_c
from trading_bot.notifications.telegram import TelegramNotifier
from trading_bot.notifications.templates import (
    daily_summary_message,
    error_message,
    risk_pause_message,
    risk_unpause_message,
    trade_close_message,
    trade_open_message,
)
from trading_bot.persistence.db import Database
from trading_bot.ranking.ranker import Ranker
from trading_bot.risk.risk_manager import RiskManager
from trading_bot.strategies.base import StrategyContext
from trading_bot.strategies.registry import StrategyRegistry
from trading_bot.strategies.selector import StrategySelector


class BotEngine:
    def __init__(self, *, config: AppConfig, db: Database) -> None:
        self.config = config
        self.db = db

        self._log = logging.getLogger("trading_bot.engine")
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name="bot-engine", daemon=True)

        self._snapshot_lock = threading.Lock()
        self._snapshot = EngineSnapshot(trading_enabled=bool(config.execution.trading_enabled))
        self._events: deque[str] = deque(maxlen=50)
        self._errors: deque[str] = deque(maxlen=50)

        self._connector: BrokerConnector | None = None
        self._scheduler = CandleCloseScheduler(timeframe=config.runtime.timeframe)
        self._universe_last_refresh_utc: datetime | None = None
        self._universe_symbols: list[str] = []
        self._symbol_meta: dict[str, SymbolMeta] = {}
        self._anchor_symbol: str | None = None

        self._pipeline: DataPipeline | None = None
        self._ranker: Ranker | None = None
        self._executor: TradeExecutor | None = None
        self._risk = RiskManager(config, db=db)

        self._registry = StrategyRegistry.default()
        self._selector = StrategySelector(config.strategy, self._registry)

        self._idempotency = IdempotencyCache()
        self._idempotency.load_recent(db=db)

        self._notifier = TelegramNotifier.from_env(
            enabled=bool(config.notifications.telegram_enabled),
            throttle_seconds=float(config.notifications.throttle_seconds),
        )
        self._risk_paused_prev: bool | None = None
        self._manual_paused: bool = False

        self._resource_monitor = ResourceMonitor()
        self._network_monitor = NetworkMonitor()
        self._deals_sync_from_utc = datetime.now(timezone.utc) - timedelta(hours=6)
        self._last_daily_summary_date: str | None = None

    def start(self) -> None:
        if self._thread.is_alive():
            return
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    def request_stop(self) -> None:
        self._stop.set()

    def enqueue(self, cmd: EngineCommand) -> None:
        self.commands.put(cmd)

    def get_snapshot(self) -> EngineSnapshot:
        with self._snapshot_lock:
            snap = EngineSnapshot(**self._snapshot.__dict__)
        return snap

    # CommandQueue is created late to avoid import cycles for UI.
    @property
    def commands(self) -> Any:
        from trading_bot.engine.state import CommandQueue

        if not hasattr(self, "_commands"):
            self._commands = CommandQueue()
        return self._commands

    # ----------------- internals -----------------

    def _set_snapshot(self, **kwargs: Any) -> None:
        with self._snapshot_lock:
            for k, v in kwargs.items():
                setattr(self._snapshot, k, v)
            self._snapshot.last_events = list(self._events)[-10:]
            self._snapshot.last_errors = list(self._errors)[-10:]

    def _event(self, msg: str) -> None:
        self._events.appendleft(msg)
        self._log.info(msg)

    def _record_error(self, msg: str, *, cycle_id: str | None = None, exc: Exception | None = None) -> None:
        self._errors.appendleft(msg)
        self._log.error(msg, extra={"cycle_id": cycle_id} if cycle_id else None)
        tb = traceback.format_exc() if exc else None
        try:
            self.db.error_repo().insert(
                severity="ERROR",
                message=msg,
                traceback=tb,
                cycle_id=cycle_id,
                context=None,
            )
        except Exception:
            pass
        self._notifier.send(error_message(message=msg, cycle_id=cycle_id), key=f"err:{msg[:60]}")

    def _run(self) -> None:
        self._event("engine started")
        while not self._stop.is_set():
            self._process_commands()
            self._update_resources_snapshot()

            if self._connector is None:
                self._connect_or_wait()
                continue

            if not self._anchor_symbol:
                self._refresh_universe(force=True)
                time.sleep(2.0)
                continue

            new_close = self._scheduler.poll(connector=self._connector, anchor_symbol=self._anchor_symbol)
            if new_close is None:
                time.sleep(float(self.config.runtime.loop_sleep_seconds))
                continue

            self._run_cycle(candle_close_time_utc=new_close)

        self._event("engine stopping")
        try:
            if self._connector is not None:
                self._connector.shutdown()
        finally:
            self.db.close_thread_connection()
        self._event("engine stopped")

    def _connect_or_wait(self) -> None:
        try:
            conn = MT5Connector.from_env(timezone=self.config.runtime.tzinfo())
            self._connector = conn
            self._pipeline = DataPipeline(
                conn,
                timeframe=self.config.runtime.timeframe,
                warmup_bars=int(self.config.runtime.warmup_bars),
            )
            self._ranker = Ranker(
                connector=conn,
                pipeline=self._pipeline,
                ranking_config=self.config.ranking,
                timeframe=self.config.runtime.timeframe,
            )
            self._executor = TradeExecutor(connector=conn, db=self.db, config=self.config)
            self._refresh_universe(force=True)
            self._deals_sync_from_utc = datetime.now(timezone.utc) - timedelta(hours=6)
            self._set_snapshot(connected=True)
            self._event("connected to MT5")
        except Exception as exc:
            self._connector = None
            self._set_snapshot(connected=False)
            self._record_error(f"MT5 connect error: {exc}", exc=exc)
            time.sleep(3.0)

    def _process_commands(self) -> None:
        while True:
            cmd = self.commands.get_nowait()
            if cmd is None:
                return
            if cmd.kind == "pause":
                self._manual_paused = True
                self._set_snapshot(paused=True)
                self._event("manual pause enabled")
            elif cmd.kind == "resume":
                self._manual_paused = False
                self._set_snapshot(paused=False)
                self._event("manual pause disabled")
            elif cmd.kind == "quit":
                self.request_stop()
                return
            elif cmd.kind == "refresh_universe":
                self._refresh_universe(force=True)
            elif cmd.kind == "apply_config":
                self._apply_config(cmd.payload.get("config") or {}, source="ui")

    def _apply_config(self, config_dict: dict[str, Any], *, source: str) -> None:
        try:
            cfg = AppConfig.model_validate(config_dict)
        except Exception as exc:
            self._record_error(f"invalid config from {source}: {exc}", exc=exc)
            return

        self.config = cfg
        try:
            self.db.settings_repo().insert_snapshot(source=source, config=config_dict)
        except Exception:
            pass

        self._risk = RiskManager(cfg, db=self.db)
        self._selector = StrategySelector(cfg.strategy, self._registry)
        self._scheduler = CandleCloseScheduler(timeframe=cfg.runtime.timeframe)

        if self._connector is not None:
            self._pipeline = DataPipeline(
                self._connector,
                timeframe=cfg.runtime.timeframe,
                warmup_bars=int(cfg.runtime.warmup_bars),
            )
            self._ranker = Ranker(
                connector=self._connector,
                pipeline=self._pipeline,
                ranking_config=cfg.ranking,
                timeframe=cfg.runtime.timeframe,
            )
            self._executor = TradeExecutor(connector=self._connector, db=self.db, config=cfg)

        self._set_snapshot(trading_enabled=bool(cfg.execution.trading_enabled))
        self._event(f"config applied ({source})")

    def _refresh_universe(self, *, force: bool) -> None:
        if self._connector is None:
            return
        interval_minutes = int(self.config.universe.discovery_interval_minutes)
        now = datetime.now(timezone.utc)
        if not force and self._universe_last_refresh_utc:
            if (now - self._universe_last_refresh_utc).total_seconds() < interval_minutes * 60:
                return

        symbols = self._connector.discover_symbols()
        meta_by_name = {s.name: s for s in symbols}
        discovered_names = set(meta_by_name.keys())

        aliases = self._load_symbol_aliases(Path("config/symbols.yaml"))
        preferred = list(self.config.universe.preferred_symbols)
        preferred_map: dict[str, str] = {}
        for canon in preferred:
            resolved = self._resolve_symbol(canon, discovered_names, aliases.get(canon, []))
            if resolved:
                preferred_map[canon] = resolved
            else:
                self._log.warning("preferred symbol not found", extra={"canonical": canon})

        universe: list[str] = []
        for canon in preferred:
            if canon in preferred_map:
                universe.append(preferred_map[canon])

        if bool(self.config.universe.use_symbol_discovery):
            allowed_classes = set()
            ac = self.config.universe.include_asset_classes
            if ac.forex:
                allowed_classes.add("forex")
            if ac.metals:
                allowed_classes.add("metals")
            if ac.indices:
                allowed_classes.add("indices")
            if ac.stocks:
                allowed_classes.add("stocks")

            per_class_limit = int(self.config.universe.discovery_limits.max_per_class)
            total_limit = int(self.config.universe.discovery_limits.max_symbols_total)

            by_class: dict[str, list[str]] = {}
            for m in symbols:
                if m.asset_class.value not in allowed_classes:
                    continue
                if m.trade_allowed is False:
                    continue
                by_class.setdefault(m.asset_class.value, []).append(m.name)

            extras: list[str] = []
            for _cls, names in by_class.items():
                for n in sorted(names)[:per_class_limit]:
                    if n not in universe and n not in extras:
                        extras.append(n)

            for n in extras:
                if len(universe) >= total_limit:
                    break
                universe.append(n)

        seen: set[str] = set()
        universe = [s for s in universe if not (s in seen or seen.add(s))]

        self._universe_symbols = universe
        self._symbol_meta = {k: v for k, v in meta_by_name.items() if k in set(universe)}
        self._anchor_symbol = universe[0] if universe else None
        self._universe_last_refresh_utc = now
        self._event(f"universe refreshed ({len(universe)} symbols)")

    def _load_symbol_aliases(self, path: Path) -> dict[str, list[str]]:
        try:
            if not path.exists():
                return {}
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            aliases = raw.get("aliases") if isinstance(raw, dict) else None
            if not isinstance(aliases, dict):
                return {}
            out: dict[str, list[str]] = {}
            for k, v in aliases.items():
                if isinstance(k, str) and isinstance(v, list):
                    out[k] = [str(x) for x in v]
            return out
        except Exception:
            return {}

    def _resolve_symbol(self, canonical: str, discovered: set[str], aliases: list[str]) -> str | None:
        candidates = [canonical] + list(aliases)
        for c in candidates:
            if c in discovered:
                return c
        lower_map = {s.lower(): s for s in discovered}
        for c in candidates:
            if c.lower() in lower_map:
                return lower_map[c.lower()]
        pref = canonical.upper()
        matches = [s for s in discovered if s.upper().startswith(pref)]
        if matches:
            matches.sort(key=len)
            return matches[0]
        return None

    def _update_resources_snapshot(self) -> None:
        res = self._resource_monitor.snapshot()
        net = self._network_monitor.rate()
        temp = best_temperature_c()
        self._set_snapshot(
            resources={
                "cpu_pct": res.cpu_pct,
                "ram_pct": res.ram_pct,
                "disk_pct": res.disk_pct,
                "uptime_seconds": res.uptime_seconds,
                "net_rx_bps": net.rx_bps,
                "net_tx_bps": net.tx_bps,
                "temp_c": temp,
            }
        )

    def _run_cycle(self, *, candle_close_time_utc: datetime) -> None:
        if self._connector is None or self._ranker is None or self._pipeline is None:
            return
        cycle_id = uuid.uuid4().hex[:12]
        start_ms = monotonic_ms()
        stage: dict[str, float] = {}
        self._log.info("cycle start", extra={"cycle_id": cycle_id, "candle_close_time_utc": iso_utc(candle_close_time_utc)})

        try:
            self._refresh_universe(force=False)
            if not self._universe_symbols:
                self._set_snapshot(
                    last_cycle_id=cycle_id,
                    last_candle_close_time_utc=iso_utc(candle_close_time_utc),
                )
                return

            t0 = monotonic_ms()
            account = self._connector.account_info()
            positions = self._connector.list_positions()
            stage["fetch_account_positions"] = monotonic_ms() - t0

            now_local = candle_close_time_utc.astimezone(self.config.runtime.tzinfo())
            eq_state = self._risk.update_equity_state(
                account=account, now_local_date=now_local.date().isoformat()
            )
            self._handle_risk_pause_state(eq_state)

            t1 = monotonic_ms()
            rank_out = self._ranker.rank(self._universe_symbols, self._symbol_meta)
            stage["rank"] = monotonic_ms() - t1

            top_views = [
                RankedSymbolView(symbol=r.symbol, score=r.score, components=r.components, reasons=r.reasons)
                for r in rank_out.selected
            ]

            pos_views = [
                PositionView(
                    symbol=p.symbol,
                    side=p.side.value,
                    volume=float(p.volume),
                    price_open=float(p.price_open),
                    sl=p.sl,
                    tp=p.tp,
                    profit=p.profit,
                )
                for p in positions
                if p.magic is None or int(p.magic) == int(self.config.execution.magic_number)
            ]

            t2 = monotonic_ms()
            self._process_top_symbols(
                cycle_id=cycle_id,
                candle_close_time_utc=candle_close_time_utc,
                rank_out=rank_out,
                positions=positions,
                account=account,
            )
            stage["strategy_risk_exec"] = monotonic_ms() - t2

            t3 = monotonic_ms()
            self._sync_deals(cycle_id=cycle_id)
            stage["sync_deals"] = monotonic_ms() - t3

            t4 = monotonic_ms()
            today = now_local.date().isoformat()
            pnl, wins, losses, equity = self._compute_today_metrics(today=today)
            stage["metrics"] = monotonic_ms() - t4

            self._maybe_send_daily_summary(
                now_local, today_pnl=pnl, wins=wins, losses=losses, equity=equity
            )

            total_ms = monotonic_ms() - start_ms
            self._log.info("cycle complete", extra={"cycle_id": cycle_id, "latency_ms": total_ms, "stage_ms": stage, "top": [v.symbol for v in top_views]})
            self._persist_heartbeat(
                cycle_id=cycle_id,
                candle_close_time_utc=candle_close_time_utc,
                latency_ms=float(total_ms),
                stage=stage,
                eq_state=eq_state,
                open_positions=len(pos_views),
            )

            self._set_snapshot(
                last_cycle_id=cycle_id,
                last_candle_close_time_utc=iso_utc(candle_close_time_utc),
                last_cycle_latency_ms=float(total_ms),
                stage_timings_ms=stage,
                top_ranked=top_views,
                open_positions=pos_views,
                today_pnl=pnl,
                wins=wins,
                losses=losses,
                trading_enabled=bool(self.config.execution.trading_enabled),
                paused=self._manual_paused or self._risk.state.paused,
            )
        except Exception as exc:
            self._record_error(f"cycle error: {exc}", cycle_id=cycle_id, exc=exc)

    def _handle_risk_pause_state(self, eq_state: dict[str, Any]) -> None:
        paused = bool(eq_state.get("paused"))
        if self._risk_paused_prev is None:
            self._risk_paused_prev = paused
            return
        if paused != self._risk_paused_prev:
            self._risk_paused_prev = paused
            if paused:
                reason = str(eq_state.get("pause_reason") or "risk pause")
                self._notifier.send(risk_pause_message(reason=reason), key="risk_pause")
            else:
                self._notifier.send(risk_unpause_message(), key="risk_unpause")

    def _process_top_symbols(
        self,
        *,
        cycle_id: str,
        candle_close_time_utc: datetime,
        rank_out: Any,
        positions: list[Position],
        account: AccountInfo | None,
    ) -> None:
        if self._connector is None or self._executor is None:
            return
        timeframe = self.config.runtime.timeframe
        candle_close_iso = iso_utc(candle_close_time_utc)

        pos_by_symbol: dict[str, Position] = {}
        for p in positions:
            if p.magic is not None and int(p.magic) != int(self.config.execution.magic_number):
                continue
            pos_by_symbol[p.symbol] = p

        manual_paused = self._manual_paused

        for r in rank_out.selected:
            sym = r.symbol
            bundle = rank_out.bundles.get(sym)
            if bundle is None or bundle.candles.empty:
                continue
            feats = bundle.features
            quote = self._connector.get_quote(sym)
            sm = self._symbol_meta.get(sym)
            if quote is None or sm is None:
                continue

            selection = self._selector.select(feats)
            if selection.strategy is None or selection.name is None:
                key = make_idempotency_key(
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    strategy="none",
                    side=Side.FLAT.value,
                )
                self.db.decision_repo().try_insert(
                    cycle_id=cycle_id,
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    rank_score=float(r.score),
                    rank_components=r.components,
                    strategy=None,
                    features=feats,
                    signal={"side": Side.FLAT.value, "reason": selection.reason},
                    risk={"paused": self._risk.state.paused, "manual_paused": manual_paused},
                    order=None,
                    result=None,
                    status=DECISION_STATUS_NO_SIGNAL,
                    idempotency_key=key,
                )
                continue

            ctx = StrategyContext(
                symbol=sym,
                timeframe=timeframe,
                candle_close_time_utc=candle_close_iso,
                quote=quote,
                symbol_meta=sm,
                current_position=pos_by_symbol.get(sym),
            )
            signal = selection.strategy.generate_signal(candles=bundle.candles, features=feats, ctx=ctx)

            # manual pause prevents sending orders, but still logs decisions
            if manual_paused:
                key = make_idempotency_key(
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    strategy=selection.name,
                    side=signal.side.value,
                )
                self.db.decision_repo().try_insert(
                    cycle_id=cycle_id,
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    rank_score=float(r.score),
                    rank_components=r.components,
                    strategy=selection.name,
                    features=feats,
                    signal=signal.__dict__,
                    risk={"allowed": False, "reason": "manual pause"},
                    order=None,
                    result=None,
                    status=DECISION_STATUS_RISK_BLOCKED,
                    idempotency_key=key,
                )
                continue

            # Exit signal
            if signal.side == Side.FLAT and "exit" in (signal.tags or []):
                if not bool(self.config.execution.close_on_exit_signal):
                    continue
                pos = pos_by_symbol.get(sym)
                if pos is None:
                    continue
                close_side = Side.SHORT if pos.side == Side.LONG else Side.LONG
                key = make_idempotency_key(
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    strategy=selection.name,
                    side=Side.FLAT.value,
                )
                rep = self._executor.close_trade(
                    cycle_id=cycle_id,
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    strategy=selection.name,
                    position_id=int(pos.position_id),
                    close_side=close_side,
                    volume=float(pos.volume),
                    idempotency_key=key,
                    rank_score=float(r.score),
                    rank_components=r.components,
                    features=feats,
                    signal=signal.__dict__,
                    risk={"paused": self._risk.state.paused, "pause_reason": self._risk.state.pause_reason},
                    reason=signal.reason,
                )
                if rep.success:
                    self._notifier.send(
                        trade_close_message(
                            symbol=sym,
                            side=pos.side.value,
                            volume=float(pos.volume),
                            profit=None,
                            reason=signal.reason,
                        ),
                        key=f"close:{sym}:{candle_close_iso}",
                    )
                continue

            # Entry signals
            if signal.side in {Side.LONG, Side.SHORT}:
                pos = pos_by_symbol.get(sym)
                if pos is not None:
                    if pos.side != signal.side:
                        close_side = Side.SHORT if pos.side == Side.LONG else Side.LONG
                        close_key = make_idempotency_key(
                            symbol=sym,
                            timeframe=timeframe,
                            candle_close_time_utc=candle_close_iso,
                            strategy=selection.name,
                            side=Side.FLAT.value,
                        )
                        rep = self._executor.close_trade(
                            cycle_id=cycle_id,
                            symbol=sym,
                            timeframe=timeframe,
                            candle_close_time_utc=candle_close_iso,
                            strategy=selection.name,
                            position_id=int(pos.position_id),
                            close_side=close_side,
                            volume=float(pos.volume),
                            idempotency_key=close_key,
                            rank_score=float(r.score),
                            rank_components=r.components,
                            features=feats,
                            signal=signal.__dict__,
                            risk={"paused": self._risk.state.paused, "pause_reason": self._risk.state.pause_reason},
                            reason="reversal",
                        )
                        if rep.success:
                            self._notifier.send(
                                trade_close_message(
                                    symbol=sym,
                                    side=pos.side.value,
                                    volume=float(pos.volume),
                                    profit=None,
                                    reason="reversal",
                                ),
                                key=f"close:{sym}:{candle_close_iso}",
                            )
                    else:
                        key = make_idempotency_key(
                            symbol=sym,
                            timeframe=timeframe,
                            candle_close_time_utc=candle_close_iso,
                            strategy=selection.name,
                            side=Side.FLAT.value,
                        )
                        self.db.decision_repo().try_insert(
                            cycle_id=cycle_id,
                            symbol=sym,
                            timeframe=timeframe,
                            candle_close_time_utc=candle_close_iso,
                            rank_score=float(r.score),
                            rank_components=r.components,
                            strategy=selection.name,
                            features=feats,
                            signal=signal.__dict__,
                            risk={"note": "already in position"},
                            order=None,
                            result=None,
                            status=DECISION_STATUS_SKIPPED,
                            idempotency_key=key,
                        )
                        continue

                risk_dec = self._risk.check_entry(
                    symbol=sym,
                    side=signal.side,
                    quote=quote,
                    symbol_meta=sm,
                    features=feats,
                    positions=positions,
                    account=account,
                )
                if not risk_dec.allowed:
                    key = make_idempotency_key(
                        symbol=sym,
                        timeframe=timeframe,
                        candle_close_time_utc=candle_close_iso,
                        strategy=selection.name,
                        side=signal.side.value,
                    )
                    self.db.decision_repo().try_insert(
                        cycle_id=cycle_id,
                        symbol=sym,
                        timeframe=timeframe,
                        candle_close_time_utc=candle_close_iso,
                        rank_score=float(r.score),
                        rank_components=r.components,
                        strategy=selection.name,
                        features=feats,
                        signal=signal.__dict__,
                        risk={"allowed": False, "reason": risk_dec.reason, "details": risk_dec.details},
                        order=None,
                        result=None,
                        status=DECISION_STATUS_RISK_BLOCKED,
                        idempotency_key=key,
                    )
                    continue

                key = make_idempotency_key(
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    strategy=selection.name,
                    side=signal.side.value,
                )
                rep = self._executor.open_trade(
                    cycle_id=cycle_id,
                    symbol=sym,
                    timeframe=timeframe,
                    candle_close_time_utc=candle_close_iso,
                    strategy=selection.name,
                    side=signal.side,
                    volume=float(risk_dec.volume or 0.0),
                    sl=risk_dec.sl,
                    tp=risk_dec.tp,
                    quote_bid=float(quote.bid),
                    quote_ask=float(quote.ask),
                    idempotency_key=key,
                    rank_score=float(r.score),
                    rank_components=r.components,
                    features=feats,
                    signal=signal.__dict__,
                    risk={"allowed": True, "reason": risk_dec.reason, "details": risk_dec.details},
                )
                if rep.success:
                    self._notifier.send(
                        trade_open_message(
                            symbol=sym,
                            side=signal.side.value,
                            volume=float(risk_dec.volume or 0.0),
                            price=float(quote.ask if signal.side == Side.LONG else quote.bid),
                            sl=risk_dec.sl,
                            tp=risk_dec.tp,
                            strategy=selection.name,
                            score=float(r.score),
                        ),
                        key=f"open:{sym}:{candle_close_iso}:{signal.side.value}",
                    )
                continue

            key = make_idempotency_key(
                symbol=sym,
                timeframe=timeframe,
                candle_close_time_utc=candle_close_iso,
                strategy=selection.name,
                side=Side.FLAT.value,
            )
            self.db.decision_repo().try_insert(
                cycle_id=cycle_id,
                symbol=sym,
                timeframe=timeframe,
                candle_close_time_utc=candle_close_iso,
                rank_score=float(r.score),
                rank_components=r.components,
                strategy=selection.name,
                features=feats,
                signal=signal.__dict__,
                risk=None,
                order=None,
                result=None,
                status=DECISION_STATUS_NO_SIGNAL,
                idempotency_key=key,
            )

    def _sync_deals(self, *, cycle_id: str) -> None:
        if self._connector is None:
            return
        now = datetime.now(timezone.utc)
        try:
            deals = self._connector.list_deals(self._deals_sync_from_utc, now)
        except Exception as exc:
            self._record_error(f"deal sync error: {exc}", cycle_id=cycle_id, exc=exc)
            return

        # keep slight overlap
        self._deals_sync_from_utc = now - timedelta(minutes=5)

        deal_dicts: list[dict[str, Any]] = []
        for d in deals:
            deal_dicts.append(
                {
                    "deal_ticket": d.deal_ticket,
                    "position_id": d.position_id,
                    "order_ticket": d.order_ticket,
                    "time_utc": iso_utc(d.time_utc),
                    "symbol": d.symbol,
                    "side": d.side.value,
                    "entry": d.entry,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "commission": d.commission,
                    "swap": d.swap,
                    "magic": d.magic,
                    "comment": d.comment,
                    "raw": d.raw,
                }
            )

        inserted = self.db.trade_repo().insert_deals(deal_dicts)
        if not inserted:
            return

        inserted_tickets = {int(d["deal_ticket"]) for d in inserted if d.get("deal_ticket") is not None}
        new_deals = [d for d in deals if int(d.deal_ticket) in inserted_tickets]
        self._risk.on_new_deals(new_deals, magic_number=int(self.config.execution.magic_number))

        for d in new_deals:
            try:
                if d.magic is not None and int(d.magic) != int(self.config.execution.magic_number):
                    continue
            except Exception:
                continue
            if str(d.entry).upper() != "OUT":
                continue
            comment = (d.comment or "").strip()
            # avoid duplicate close notifications for bot-initiated closes (we already notify on execution)
            if comment.lower().startswith("tb:"):
                continue
            self._notifier.send(
                trade_close_message(
                    symbol=d.symbol,
                    side=d.side.value,
                    volume=float(d.volume),
                    profit=float(d.profit) if d.profit is not None else None,
                    reason=comment or None,
                ),
                key=f"deal_close:{d.deal_ticket}",
            )

    def _compute_today_metrics(self, *, today: str) -> tuple[float | None, int, int, float | None]:
        try:
            rows = self.db.query_all(
                "SELECT profit, magic, entry, time_utc FROM trades WHERE substr(time_utc,1,10)=? ORDER BY id DESC",
                (today,),
            )
        except Exception:
            return None, 0, 0, None

        pnl = 0.0
        wins = 0
        losses = 0
        for r in rows:
            try:
                if r["magic"] is not None and int(r["magic"]) != int(self.config.execution.magic_number):
                    continue
            except Exception:
                continue
            if str(r["entry"] or "").upper() != "OUT":
                continue
            if r["profit"] is None:
                continue
            pr = float(r["profit"])
            pnl += pr
            if pr >= 0:
                wins += 1
            else:
                losses += 1

        equity = None
        try:
            hb = self.db.heartbeat_repo().latest()
            equity = hb.get("equity") if hb else None
        except Exception:
            equity = None
        return pnl, wins, losses, float(equity) if equity is not None else None

    def _maybe_send_daily_summary(
        self,
        now_local: datetime,
        *,
        today_pnl: float | None,
        wins: int,
        losses: int,
        equity: float | None,
    ) -> None:
        target = self.config.notifications.daily_summary_time_obj()
        date = now_local.date().isoformat()
        if self._last_daily_summary_date == date:
            return
        if now_local.time() < target:
            return
        self._last_daily_summary_date = date
        self._notifier.send(
            daily_summary_message(date=date, pnl=today_pnl, wins=wins, losses=losses, equity=equity),
            key=f"daily:{date}",
        )

    def _persist_heartbeat(
        self,
        *,
        cycle_id: str,
        candle_close_time_utc: datetime,
        latency_ms: float,
        stage: dict[str, float],
        eq_state: dict[str, Any],
        open_positions: int,
    ) -> None:
        res = self._snapshot.resources
        payload = {
            "cycle_id": cycle_id,
            "status": "ok",
            "cycle_latency_ms": latency_ms,
            "mt5_connected": 1 if self._connector is not None else 0,
            "equity": eq_state.get("equity"),
            "balance": eq_state.get("balance"),
            "daily_start_equity": eq_state.get("daily_start_equity"),
            "daily_pnl": eq_state.get("daily_pnl"),
            "peak_equity": eq_state.get("peak_equity"),
            "drawdown_pct": eq_state.get("drawdown_pct"),
            "open_positions": int(open_positions),
            "cpu_pct": res.get("cpu_pct"),
            "ram_pct": res.get("ram_pct"),
            "disk_pct": res.get("disk_pct"),
            "net_rx_bps": res.get("net_rx_bps"),
            "net_tx_bps": res.get("net_tx_bps"),
            "temp_c": res.get("temp_c"),
            "extra": {"stage_timings_ms": stage, "candle_close_time_utc": iso_utc(candle_close_time_utc)},
        }
        try:
            self.db.heartbeat_repo().insert(payload)
        except Exception:
            pass
