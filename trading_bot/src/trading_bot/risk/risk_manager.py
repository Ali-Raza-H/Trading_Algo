from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from trading_bot.connectors.base import AccountInfo, Deal, Position, Quote, Side, SymbolMeta
from trading_bot.core.config import AppConfig
from trading_bot.core.utils import clamp
from trading_bot.risk.limits import PositionCounts, count_positions, daily_loss_pct, drawdown_pct
from trading_bot.risk.models import RiskDecision, RiskState
from trading_bot.risk.sizing import compute_volume
from trading_bot.risk.sltp import SLTP, sltp_atr, sltp_rr


class RiskManager:
    def __init__(self, config: AppConfig, *, db: Any) -> None:
        self.cfg = config
        self.db = db
        self._log = logging.getLogger("trading_bot.risk")
        self.state = RiskState()
        self._load_from_heartbeat()

    def _load_from_heartbeat(self) -> None:
        try:
            hb = self.db.heartbeat_repo().latest()
        except Exception:
            return
        if not hb:
            return
        self.state.daily_start_equity = hb.get("daily_start_equity")
        self.state.peak_equity = hb.get("peak_equity")
        # daily_date not stored explicitly; infer from created_at in runtime tz by engine (not here).

    def on_new_deals(self, deals: list[Deal], *, magic_number: int) -> None:
        # Track loss streak based on closes (DEAL_ENTRY_OUT) for bot magic.
        for d in deals:
            try:
                if d.magic is not None and int(d.magic) != int(magic_number):
                    continue
            except Exception:
                continue
            if str(d.entry).upper() != "OUT":
                continue
            profit = float(d.profit or 0.0)
            if profit < 0:
                self.state.loss_streak += 1
            else:
                self.state.loss_streak = 0

            if self.cfg.risk.cooloff.enabled and self.state.loss_streak >= int(self.cfg.risk.cooloff.losses):
                self.state.cooloff_until_utc = datetime.now(timezone.utc) + timedelta(
                    minutes=int(self.cfg.risk.cooloff.minutes)
                )
                self._log.warning(
                    "cooloff engaged",
                    extra={
                        "loss_streak": self.state.loss_streak,
                        "cooloff_until_utc": self.state.cooloff_until_utc.isoformat(),
                    },
                )

    def update_equity_state(
        self,
        *,
        account: AccountInfo | None,
        now_local_date: str,
    ) -> dict[str, Any]:
        """
        Update daily start equity / peak equity tracking and evaluate global risk.
        Returns dict suitable for persistence/UI.
        """
        equity = float(account.equity) if account and account.equity is not None else None
        balance = float(account.balance) if account and account.balance is not None else None

        if self.state.daily_date != now_local_date:
            self.state.daily_date = now_local_date
            if equity is not None and equity > 0:
                self.state.daily_start_equity = equity
            self.state.loss_streak = 0
            self.state.cooloff_until_utc = None

        if equity is not None and equity > 0:
            if self.state.peak_equity is None or equity > self.state.peak_equity:
                self.state.peak_equity = equity

        dd = None
        dl = None
        if equity is not None and self.state.peak_equity:
            dd = drawdown_pct(peak_equity=float(self.state.peak_equity), equity=equity)
        if equity is not None and self.state.daily_start_equity:
            dl = daily_loss_pct(daily_start_equity=float(self.state.daily_start_equity), equity=equity)

        pause_reason = None
        paused = False
        if dl is not None and dl >= float(self.cfg.risk.max_daily_loss_pct):
            paused = True
            pause_reason = f"max daily loss breached ({dl:.2%} >= {self.cfg.risk.max_daily_loss_pct:.2%})"
        if dd is not None and dd >= float(self.cfg.risk.max_drawdown_pct):
            paused = True
            pause_reason = f"max drawdown breached ({dd:.2%} >= {self.cfg.risk.max_drawdown_pct:.2%})"
        if self.state.cooloff_until_utc and datetime.now(timezone.utc) < self.state.cooloff_until_utc:
            paused = True
            pause_reason = f"cooloff until {self.state.cooloff_until_utc.isoformat()}"

        self.state.paused = paused
        self.state.pause_reason = pause_reason

        return {
            "equity": equity,
            "balance": balance,
            "daily_start_equity": self.state.daily_start_equity,
            "daily_pnl": (equity - self.state.daily_start_equity) if (equity is not None and self.state.daily_start_equity) else None,
            "peak_equity": self.state.peak_equity,
            "drawdown_pct": dd,
            "daily_loss_pct": dl,
            "paused": paused,
            "pause_reason": pause_reason,
            "loss_streak": self.state.loss_streak,
            "cooloff_until_utc": self.state.cooloff_until_utc.isoformat() if self.state.cooloff_until_utc else None,
        }

    def check_entry(
        self,
        *,
        symbol: str,
        side: Side,
        quote: Quote,
        symbol_meta: SymbolMeta,
        features: dict[str, Any],
        positions: list[Position],
        account: AccountInfo | None,
    ) -> RiskDecision:
        if side not in {Side.LONG, Side.SHORT}:
            return RiskDecision(allowed=False, reason="side is not entry", side=side)
        if self.state.paused:
            return RiskDecision(
                allowed=False,
                reason=self.state.pause_reason or "risk paused",
                side=side,
                details={"paused": True},
            )

        counts = count_positions(positions, magic=self.cfg.execution.magic_number)
        if counts.total >= int(self.cfg.risk.max_open_positions_total):
            return RiskDecision(
                allowed=False,
                reason=f"max open positions reached ({counts.total})",
                side=side,
                details={"open_positions_total": counts.total},
            )
        if counts.per_symbol.get(symbol, 0) >= int(self.cfg.risk.max_open_positions_per_symbol):
            return RiskDecision(
                allowed=False,
                reason=f"max positions for symbol reached ({symbol})",
                side=side,
                details={"open_positions_symbol": counts.per_symbol.get(symbol, 0)},
            )

        point = float(symbol_meta.point or 0.0)
        if point <= 0:
            return RiskDecision(allowed=False, reason="symbol point missing", side=side)

        entry = quote.ask if side == Side.LONG else quote.bid
        sltp = self._compute_sltp(side=side, entry=entry, point=point, features=features)
        if sltp.sl is None or sltp.tp is None:
            return RiskDecision(allowed=False, reason="failed to compute SL/TP", side=side)

        stop_points = self._stop_points(side=side, entry=entry, sl=sltp.sl, point=point)
        equity = float(account.equity) if account and account.equity is not None else 0.0
        vol_res = compute_volume(
            equity=equity,
            risk_per_trade=float(self.cfg.risk.risk_per_trade),
            stop_points=stop_points,
            symbol=symbol_meta,
        )
        if not vol_res.ok or not vol_res.volume:
            return RiskDecision(allowed=False, reason=f"sizing blocked: {vol_res.reason}", side=side)

        return RiskDecision(
            allowed=True,
            reason="ok",
            side=side,
            volume=float(vol_res.volume),
            sl=float(sltp.sl),
            tp=float(sltp.tp),
            details={
                "entry": float(entry),
                "stop_points": float(stop_points),
                "volume_reason": vol_res.reason,
                "sltp_mode": self.cfg.risk.sltp_mode,
            },
        )

    def _compute_sltp(self, *, side: Side, entry: float, point: float, features: dict[str, Any]) -> SLTP:
        if self.cfg.risk.sltp_mode == "atr":
            atr14 = float(features.get("atr14") or 0.0)
            return sltp_atr(
                side=side,
                entry=float(entry),
                atr=atr14,
                sl_mult=float(self.cfg.risk.atr.sl_mult),
                tp_mult=float(self.cfg.risk.atr.tp_mult),
            )
        return sltp_rr(
            side=side,
            entry=float(entry),
            point=float(point),
            stop_points=int(self.cfg.risk.rr.stop_points),
            take_points=int(self.cfg.risk.rr.take_points),
        )

    def _stop_points(self, *, side: Side, entry: float, sl: float, point: float) -> float:
        if point <= 0:
            return 0.0
        dist = abs(entry - sl)
        return dist / point

