from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

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
from trading_bot.core.exceptions import BrokerDisconnectedError, BrokerError, RetryableBrokerError
from trading_bot.core.timeframes import timeframe_to_mt5


def _dt_utc_from_epoch(seconds: int | float) -> datetime:
    return datetime.fromtimestamp(float(seconds), tz=timezone.utc)


def _safe_get(obj: Any, name: str, default: Any = None) -> Any:
    try:
        return getattr(obj, name)
    except Exception:
        return default


class MT5Connector(BrokerConnector):
    def __init__(
        self,
        *,
        login: int,
        password: str,
        server: str,
        timezone: ZoneInfo,
        path: str | None = None,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        self._log = logging.getLogger("trading_bot.mt5")
        self._login = int(login)
        self._password = password
        self._server = server
        self._path = path
        self._tz = timezone
        self._connect_timeout_seconds = connect_timeout_seconds

        try:
            import MetaTrader5 as mt5  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise BrokerError(
                "Failed to import MetaTrader5. On Linux, the official package "
                "requires running under Wine + Windows Python."
            ) from exc
        self._mt5 = mt5

        self._ensure_connected(retries=3)

    @classmethod
    def from_env(cls, *, timezone: ZoneInfo) -> "MT5Connector":
        login = os.getenv("MT5_LOGIN")
        password = os.getenv("MT5_PASSWORD")
        server = os.getenv("MT5_SERVER")
        path = os.getenv("MT5_PATH") or None
        missing = [k for k, v in [("MT5_LOGIN", login), ("MT5_PASSWORD", password), ("MT5_SERVER", server)] if not v]
        if missing:
            raise BrokerError(f"Missing required MT5 env vars: {', '.join(missing)}")
        return cls(login=int(login), password=str(password), server=str(server), timezone=timezone, path=path)

    def shutdown(self) -> None:
        try:
            self._mt5.shutdown()
        except Exception:
            pass

    def _initialize(self) -> None:
        ok = self._mt5.initialize(
            path=self._path,
            login=self._login,
            password=self._password,
            server=self._server,
        )
        if not ok:
            code, msg = self._mt5.last_error()
            raise BrokerDisconnectedError(f"mt5.initialize failed: {code} {msg}")

    def _connected(self) -> bool:
        try:
            ti = self._mt5.terminal_info()
            ai = self._mt5.account_info()
            return ti is not None and ai is not None
        except Exception:
            return False

    def _ensure_connected(self, retries: int = 1) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            if self._connected():
                return
            try:
                try:
                    self._mt5.shutdown()
                except Exception:
                    pass
                self._initialize()
                if self._connected():
                    self._log.info("mt5 connected", extra={"server": self._server, "login": self._login})
                    return
            except Exception as exc:
                last_exc = exc
                self._log.warning(
                    "mt5 connect failed",
                    extra={"attempt": attempt, "retries": retries, "error": str(exc)},
                )
                time.sleep(min(2.0 * attempt, 5.0))
        raise BrokerDisconnectedError(str(last_exc) if last_exc else "mt5 not connected")

    def _call(self, fn_name: str, *args: Any, **kwargs: Any) -> Any:
        self._ensure_connected(retries=2)
        fn = getattr(self._mt5, fn_name)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            raise RetryableBrokerError(f"MT5 call failed: {fn_name}: {exc}") from exc

    def account_info(self) -> AccountInfo | None:
        self._ensure_connected(retries=2)
        ai = self._mt5.account_info()
        if ai is None:
            return None
        raw = {k: _safe_get(ai, k) for k in dir(ai) if not k.startswith("_")}
        trade_mode_raw = _safe_get(ai, "trade_mode")
        trade_mode = AccountTradeMode.UNKNOWN
        try:
            if trade_mode_raw == self._mt5.ACCOUNT_TRADE_MODE_DEMO:
                trade_mode = AccountTradeMode.DEMO
            elif trade_mode_raw == self._mt5.ACCOUNT_TRADE_MODE_REAL:
                trade_mode = AccountTradeMode.REAL
            elif trade_mode_raw == self._mt5.ACCOUNT_TRADE_MODE_CONTEST:
                trade_mode = AccountTradeMode.CONTEST
        except Exception:
            trade_mode = AccountTradeMode.UNKNOWN
        return AccountInfo(
            login=_safe_get(ai, "login"),
            server=_safe_get(ai, "server"),
            currency=_safe_get(ai, "currency"),
            leverage=_safe_get(ai, "leverage"),
            balance=_safe_get(ai, "balance"),
            equity=_safe_get(ai, "equity"),
            margin=_safe_get(ai, "margin"),
            trade_mode=trade_mode,
            name=_safe_get(ai, "name"),
            company=_safe_get(ai, "company"),
            raw=raw,
        )

    def discover_symbols(self) -> list[SymbolMeta]:
        syms = self._call("symbols_get")
        if syms is None:
            return []
        out: list[SymbolMeta] = []
        for s in syms:
            out.append(self._symbol_meta_from_info(s))
        return out

    def get_symbol_info(self, symbol: str) -> SymbolMeta | None:
        info = self._call("symbol_info", symbol)
        if info is None:
            return None
        return self._symbol_meta_from_info(info)

    def get_quote(self, symbol: str) -> Quote | None:
        tick = self._call("symbol_info_tick", symbol)
        if tick is None:
            return None
        info = self._call("symbol_info", symbol)
        point = float(_safe_get(info, "point", 0.0) or 0.0)
        bid = float(_safe_get(tick, "bid", 0.0) or 0.0)
        ask = float(_safe_get(tick, "ask", 0.0) or 0.0)
        if bid <= 0 or ask <= 0 or point <= 0:
            return None
        spread_points = (ask - bid) / point if point else float("inf")
        return Quote(
            symbol=symbol,
            bid=bid,
            ask=ask,
            time_utc=_dt_utc_from_epoch(_safe_get(tick, "time", 0) or 0),
            spread_points=float(spread_points),
        )

    def get_candles(self, symbol: str, timeframe: str, n: int) -> pd.DataFrame:
        tf = timeframe_to_mt5(timeframe)
        rates = self._call("copy_rates_from_pos", symbol, tf, 0, int(n))
        if rates is None:
            return pd.DataFrame()
        df = pd.DataFrame(rates)
        if df.empty:
            return df
        df["time_utc"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df["time_local"] = df["time_utc"].dt.tz_convert(self._tz)
        df = df.sort_values("time_utc").reset_index(drop=True)
        return df

    def list_positions(self) -> list[Position]:
        positions = self._call("positions_get")
        if positions is None:
            return []
        out: list[Position] = []
        for p in positions:
            raw = {k: _safe_get(p, k) for k in dir(p) if not k.startswith("_")}
            symbol = str(_safe_get(p, "symbol"))
            typ = _safe_get(p, "type")
            side = Side.LONG
            try:
                if typ == self._mt5.POSITION_TYPE_SELL:
                    side = Side.SHORT
            except Exception:
                pass
            out.append(
                Position(
                    position_id=int(_safe_get(p, "ticket")),
                    symbol=symbol,
                    side=side,
                    volume=float(_safe_get(p, "volume", 0.0) or 0.0),
                    price_open=float(_safe_get(p, "price_open", 0.0) or 0.0),
                    sl=_safe_get(p, "sl"),
                    tp=_safe_get(p, "tp"),
                    time_utc=_dt_utc_from_epoch(_safe_get(p, "time", 0) or 0),
                    profit=_safe_get(p, "profit"),
                    swap=_safe_get(p, "swap"),
                    commission=_safe_get(p, "commission"),
                    magic=_safe_get(p, "magic"),
                    comment=_safe_get(p, "comment"),
                    raw=raw,
                )
            )
        return out

    def list_deals(self, from_utc: datetime, to_utc: datetime) -> list[Deal]:
        deals = self._call("history_deals_get", from_utc, to_utc)
        if deals is None:
            return []
        out: list[Deal] = []
        for d in deals:
            raw = {k: _safe_get(d, k) for k in dir(d) if not k.startswith("_")}
            symbol = str(_safe_get(d, "symbol"))
            typ = _safe_get(d, "type")
            side = Side.LONG
            try:
                if typ == self._mt5.DEAL_TYPE_SELL:
                    side = Side.SHORT
            except Exception:
                pass
            entry = str(_safe_get(d, "entry"))
            try:
                if _safe_get(d, "entry") == self._mt5.DEAL_ENTRY_IN:
                    entry = "IN"
                elif _safe_get(d, "entry") == self._mt5.DEAL_ENTRY_OUT:
                    entry = "OUT"
            except Exception:
                entry = str(_safe_get(d, "entry"))
            out.append(
                Deal(
                    deal_ticket=int(_safe_get(d, "ticket")),
                    position_id=_safe_get(d, "position_id"),
                    order_ticket=_safe_get(d, "order"),
                    time_utc=_dt_utc_from_epoch(_safe_get(d, "time", 0) or 0),
                    symbol=symbol,
                    side=side,
                    entry=entry,
                    volume=float(_safe_get(d, "volume", 0.0) or 0.0),
                    price=float(_safe_get(d, "price", 0.0) or 0.0),
                    profit=_safe_get(d, "profit"),
                    commission=_safe_get(d, "commission"),
                    swap=_safe_get(d, "swap"),
                    magic=_safe_get(d, "magic"),
                    comment=_safe_get(d, "comment"),
                    raw=raw,
                )
            )
        return out

    def modify_position(self, *, position_id: int, sl: float | None, tp: float | None) -> bool:
        req = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "position": int(position_id),
            "sl": float(sl) if sl is not None else 0.0,
            "tp": float(tp) if tp is not None else 0.0,
        }
        res = self._call("order_send", req)
        return res is not None and _safe_get(res, "retcode") in {
            getattr(self._mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(self._mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
        }

    def place_order(self, req: OrderRequest) -> OrderResult:
        if req.side not in {Side.LONG, Side.SHORT}:
            raise BrokerError(f"Unsupported order side: {req.side}")

        info = self._call("symbol_info", req.symbol)
        if info is None:
            raise BrokerError(f"Unknown symbol: {req.symbol}")
        if not self._call("symbol_select", req.symbol, True):
            raise BrokerError(f"symbol_select failed: {req.symbol}")

        tick = self._call("symbol_info_tick", req.symbol)
        if tick is None:
            raise RetryableBrokerError(f"No tick for symbol: {req.symbol}")

        point = float(_safe_get(info, "point", 0.0) or 0.0)
        stops_level = int(_safe_get(info, "trade_stops_level", 0) or 0)
        price = float(_safe_get(tick, "ask") if req.side == Side.LONG else _safe_get(tick, "bid"))
        if price <= 0:
            raise RetryableBrokerError("Invalid price from tick")

        order_type = self._mt5.ORDER_TYPE_BUY if req.side == Side.LONG else self._mt5.ORDER_TYPE_SELL
        filling = self._choose_filling_mode(info)

        sl = self._enforce_stops(req.side, price, req.sl, point, stops_level, is_sl=True)
        tp = self._enforce_stops(req.side, price, req.tp, point, stops_level, is_sl=False)

        request: dict[str, Any] = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": req.symbol,
            "volume": float(req.volume),
            "type": order_type,
            "price": float(price),
            "deviation": int(req.deviation_points),
            "magic": int(req.magic),
            "comment": str(req.comment)[:31],
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        if sl is not None:
            request["sl"] = float(sl)
        if tp is not None:
            request["tp"] = float(tp)
        if req.position_id is not None:
            request["position"] = int(req.position_id)

        res = self._call("order_send", request)
        if res is None:
            code, msg = self._mt5.last_error()
            return OrderResult(
                success=False,
                retcode=code,
                order_ticket=None,
                position_id=req.position_id,
                comment=f"order_send returned None: {msg}",
                raw={"request": request, "last_error": [code, msg]},
            )
        retcode = int(_safe_get(res, "retcode", -1) or -1)
        success_codes = {
            getattr(self._mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(self._mt5, "TRADE_RETCODE_PLACED", 10008),
            getattr(self._mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
        }
        order_ticket = _safe_get(res, "order")
        deal_ticket = _safe_get(res, "deal")
        comment = _safe_get(res, "comment")
        success = retcode in success_codes
        raw = {"retcode": retcode, "order": order_ticket, "deal": deal_ticket, "comment": comment, "request": request}
        return OrderResult(
            success=bool(success),
            retcode=retcode,
            order_ticket=int(order_ticket) if order_ticket else None,
            position_id=int(req.position_id) if req.position_id else None,
            comment=str(comment) if comment is not None else None,
            raw=raw,
        )

    def _choose_filling_mode(self, info: Any) -> int:
        # Prefer IOC; fallback to whatever is supported by the symbol.
        try:
            return self._mt5.ORDER_FILLING_IOC
        except Exception:
            pass
        return int(_safe_get(info, "filling_mode", 0) or 0)

    def _enforce_stops(
        self,
        side: Side,
        price: float,
        level: float | None,
        point: float,
        stops_level: int,
        *,
        is_sl: bool,
    ) -> float | None:
        if level is None:
            return None
        if stops_level <= 0 or point <= 0:
            return float(level)
        min_dist = stops_level * point
        if side == Side.LONG:
            if is_sl:
                return float(min(level, price - min_dist))
            return float(max(level, price + min_dist))
        # short
        if is_sl:
            return float(max(level, price + min_dist))
        return float(min(level, price - min_dist))

    def _symbol_meta_from_info(self, info: Any) -> SymbolMeta:
        name = str(_safe_get(info, "name"))
        desc = _safe_get(info, "description")
        path = _safe_get(info, "path")
        asset_class = self._classify_symbol(name, str(path or ""), str(desc or ""))
        extra = {}
        for k in (
            "trade_calc_mode",
            "trade_contract_size",
            "trade_tick_size",
            "trade_tick_value",
            "trade_tick_value_profit",
            "trade_tick_value_loss",
        ):
            extra[k] = _safe_get(info, k)
        return SymbolMeta(
            name=name,
            description=str(desc) if desc is not None else None,
            path=str(path) if path is not None else None,
            asset_class=asset_class,
            currency_base=_safe_get(info, "currency_base"),
            currency_profit=_safe_get(info, "currency_profit"),
            currency_margin=_safe_get(info, "currency_margin"),
            digits=_safe_get(info, "digits"),
            point=_safe_get(info, "point"),
            trade_mode=_safe_get(info, "trade_mode"),
            trade_allowed=_safe_get(info, "trade_allowed"),
            spread_points=_safe_get(info, "spread"),
            trade_stops_level=_safe_get(info, "trade_stops_level"),
            volume_min=_safe_get(info, "volume_min"),
            volume_max=_safe_get(info, "volume_max"),
            volume_step=_safe_get(info, "volume_step"),
            trade_tick_value=_safe_get(info, "trade_tick_value"),
            trade_tick_size=_safe_get(info, "trade_tick_size"),
            trade_contract_size=_safe_get(info, "trade_contract_size"),
            extra=extra,
        )

    def _classify_symbol(self, name: str, path: str, description: str) -> AssetClass:
        s = f"{name} {path} {description}".lower()
        if "xau" in name.lower() or "xag" in name.lower() or "gold" in s or "silver" in s:
            return AssetClass.METALS
        if "forex" in s or "fx" in s:
            return AssetClass.FOREX
        if re.fullmatch(r"[A-Za-z]{6,7}", name) and name[:3].isalpha() and name[3:6].isalpha():
            return AssetClass.FOREX
        if any(k in s for k in ("index", "indices", "cash", "us30", "spx", "nas", "dax", "ger", "uk100")):
            return AssetClass.INDICES
        if any(k in s for k in ("stocks", "shares", "equities", "equity")):
            return AssetClass.STOCKS
        return AssetClass.UNKNOWN

