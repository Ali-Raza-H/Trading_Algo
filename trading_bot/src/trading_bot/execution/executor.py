from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any

from trading_bot.connectors.base import AccountTradeMode, BrokerConnector, OrderRequest, Side
from trading_bot.core.constants import (
    DECISION_STATUS_CLOSED,
    DECISION_STATUS_ERROR,
    DECISION_STATUS_OPENED,
    DECISION_STATUS_SKIPPED,
)
from trading_bot.core.exceptions import BrokerError
from trading_bot.core.utils import safe_json_dumps
from trading_bot.execution.models import ExecutionReport
from trading_bot.execution.retry import call_with_retries


class TradeExecutor:
    def __init__(
        self,
        *,
        connector: BrokerConnector,
        db: Any,
        config: Any,
    ) -> None:
        self.connector = connector
        self.db = db
        self.cfg = config
        self._log = logging.getLogger("trading_bot.exec")
        self._verify_delay_seconds = 0.3

    def open_trade(
        self,
        *,
        cycle_id: str,
        symbol: str,
        timeframe: str,
        candle_close_time_utc: str,
        strategy: str,
        side: Side,
        volume: float,
        sl: float | None,
        tp: float | None,
        quote_bid: float,
        quote_ask: float,
        idempotency_key: str,
        rank_score: float | None,
        rank_components: dict[str, Any] | None,
        features: dict[str, Any] | None,
        signal: dict[str, Any] | None,
        risk: dict[str, Any] | None,
    ) -> ExecutionReport:
        if not bool(self.cfg.execution.trading_enabled):
            return ExecutionReport(action="open", success=False, reason="trading disabled")

        ai = self.connector.account_info()
        if ai and ai.trade_mode not in {AccountTradeMode.DEMO, AccountTradeMode.CONTEST}:
            return ExecutionReport(
                action="open",
                success=False,
                reason=f"paper-only gate: trade_mode={ai.trade_mode}",
            )

        order_req = OrderRequest(
            symbol=symbol,
            side=side,
            volume=float(volume),
            sl=sl,
            tp=tp,
            deviation_points=int(self.cfg.execution.slippage_points),
            magic=int(self.cfg.execution.magic_number),
            comment=f"tb:{idempotency_key[:12]}",
            idempotency_key=idempotency_key,
            position_id=None,
        )
        order_json = asdict(order_req)

        inserted = self.db.decision_repo().try_insert(
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=timeframe,
            candle_close_time_utc=candle_close_time_utc,
            rank_score=rank_score,
            rank_components=rank_components,
            strategy=strategy,
            features=features,
            signal=signal,
            risk=risk,
            order=order_json,
            result=None,
            status=DECISION_STATUS_SKIPPED,
            idempotency_key=idempotency_key,
        )
        if not inserted:
            return ExecutionReport(action="open", success=False, reason="duplicate idempotency key")

        def _send() -> Any:
            return self.connector.place_order(order_req)

        try:
            res = call_with_retries(
                _send,
                max_attempts=int(self.cfg.execution.retries.max_attempts),
                backoff_seconds=list(self.cfg.execution.retries.backoff_seconds),
            )
        except Exception as exc:
            self._update_decision(idempotency_key, status=DECISION_STATUS_ERROR, result={"error": str(exc)})
            return ExecutionReport(action="open", success=False, reason=str(exc), order=order_json)

        result_json = res.raw if hasattr(res, "raw") else {}
        if not res.success:
            self._update_decision(
                idempotency_key,
                status=DECISION_STATUS_ERROR,
                result={"success": False, **result_json},
            )
            return ExecutionReport(action="open", success=False, reason=f"retcode={res.retcode}", order=order_json, result=result_json)

        self._update_decision(
            idempotency_key,
            status=DECISION_STATUS_OPENED,
            result={"success": True, **result_json},
        )
        self._verify_open(symbol=symbol)
        return ExecutionReport(action="open", success=True, reason="opened", order=order_json, result=result_json)

    def close_trade(
        self,
        *,
        cycle_id: str,
        symbol: str,
        timeframe: str,
        candle_close_time_utc: str,
        strategy: str,
        position_id: int,
        close_side: Side,
        volume: float,
        idempotency_key: str,
        rank_score: float | None,
        rank_components: dict[str, Any] | None,
        features: dict[str, Any] | None,
        signal: dict[str, Any] | None,
        risk: dict[str, Any] | None,
        reason: str,
    ) -> ExecutionReport:
        if not bool(self.cfg.execution.trading_enabled):
            return ExecutionReport(action="close", success=False, reason="trading disabled")

        ai = self.connector.account_info()
        if ai and ai.trade_mode not in {AccountTradeMode.DEMO, AccountTradeMode.CONTEST}:
            return ExecutionReport(
                action="close",
                success=False,
                reason=f"paper-only gate: trade_mode={ai.trade_mode}",
            )

        order_req = OrderRequest(
            symbol=symbol,
            side=close_side,
            volume=float(volume),
            sl=None,
            tp=None,
            deviation_points=int(self.cfg.execution.slippage_points),
            magic=int(self.cfg.execution.magic_number),
            comment=f"tb:{idempotency_key[:12]}",
            idempotency_key=idempotency_key,
            position_id=int(position_id),
        )
        order_json = asdict(order_req)

        inserted = self.db.decision_repo().try_insert(
            cycle_id=cycle_id,
            symbol=symbol,
            timeframe=timeframe,
            candle_close_time_utc=candle_close_time_utc,
            rank_score=rank_score,
            rank_components=rank_components,
            strategy=strategy,
            features=features,
            signal=signal,
            risk=risk,
            order=order_json,
            result=None,
            status=DECISION_STATUS_SKIPPED,
            idempotency_key=idempotency_key,
        )
        if not inserted:
            return ExecutionReport(action="close", success=False, reason="duplicate idempotency key")

        def _send() -> Any:
            return self.connector.place_order(order_req)

        try:
            res = call_with_retries(
                _send,
                max_attempts=int(self.cfg.execution.retries.max_attempts),
                backoff_seconds=list(self.cfg.execution.retries.backoff_seconds),
            )
        except Exception as exc:
            self._update_decision(idempotency_key, status=DECISION_STATUS_ERROR, result={"error": str(exc), "reason": reason})
            return ExecutionReport(action="close", success=False, reason=str(exc), order=order_json)

        result_json = res.raw if hasattr(res, "raw") else {}
        if not res.success:
            self._update_decision(
                idempotency_key,
                status=DECISION_STATUS_ERROR,
                result={"success": False, "reason": reason, **result_json},
            )
            return ExecutionReport(action="close", success=False, reason=f"retcode={res.retcode}", order=order_json, result=result_json)

        self._update_decision(
            idempotency_key,
            status=DECISION_STATUS_CLOSED,
            result={"success": True, "reason": reason, **result_json},
        )
        self._verify_closed(position_id=position_id)
        return ExecutionReport(action="close", success=True, reason="closed", order=order_json, result=result_json)

    def _update_decision(self, idempotency_key: str, *, status: str, result: dict[str, Any] | None) -> None:
        try:
            self.db.conn().execute(
                "UPDATE decisions SET status=?, result_json=? WHERE idempotency_key=?",
                (status, safe_json_dumps(result) if result is not None else None, idempotency_key),
            )
        except Exception as exc:
            self._log.error("failed updating decision", extra={"error": str(exc), "idempotency_key": idempotency_key})

    def _verify_open(self, *, symbol: str) -> None:
        try:
            time.sleep(self._verify_delay_seconds)
            positions = self.connector.list_positions()
            magic = int(self.cfg.execution.magic_number)
            if any(p.symbol == symbol and (p.magic is None or int(p.magic) == magic) for p in positions):
                return
            self._log.warning("post-trade verification: position not found", extra={"symbol": symbol})
        except Exception as exc:
            self._log.debug("post-trade verification failed", extra={"error": str(exc)})

    def _verify_closed(self, *, position_id: int) -> None:
        try:
            time.sleep(self._verify_delay_seconds)
            positions = self.connector.list_positions()
            if any(int(p.position_id) == int(position_id) for p in positions):
                self._log.warning("post-trade verification: position still present", extra={"position_id": position_id})
        except Exception as exc:
            self._log.debug("post-close verification failed", extra={"error": str(exc)})
