from __future__ import annotations

from datetime import datetime
from typing import Any


def trade_open_message(*, symbol: str, side: str, volume: float, price: float | None, sl: float | None, tp: float | None, strategy: str, score: float | None) -> str:
    parts = [
        "📈 Trade OPEN",
        f"Symbol: {symbol}",
        f"Side: {side}",
        f"Volume: {volume:g}",
        f"Strategy: {strategy}",
    ]
    if score is not None:
        parts.append(f"Rank score: {score:.3f}")
    if price is not None:
        parts.append(f"Price: {price:g}")
    if sl is not None:
        parts.append(f"SL: {sl:g}")
    if tp is not None:
        parts.append(f"TP: {tp:g}")
    return "\n".join(parts)


def trade_close_message(*, symbol: str, side: str, volume: float, profit: float | None, reason: str | None = None) -> str:
    parts = ["📉 Trade CLOSE", f"Symbol: {symbol}", f"Side: {side}", f"Volume: {volume:g}"]
    if profit is not None:
        parts.append(f"Profit: {profit:g}")
    if reason:
        parts.append(f"Reason: {reason}")
    return "\n".join(parts)


def risk_pause_message(*, reason: str) -> str:
    return "\n".join(["⛔ Trading PAUSED", f"Reason: {reason}"])


def risk_unpause_message() -> str:
    return "✅ Trading UNPAUSED"


def error_message(*, message: str, cycle_id: str | None = None) -> str:
    if cycle_id:
        return f"⚠️ Error (cycle {cycle_id})\n{message}"
    return f"⚠️ Error\n{message}"


def daily_summary_message(*, date: str, pnl: float | None, wins: int, losses: int, equity: float | None) -> str:
    parts = [f"🧾 Daily Summary ({date})"]
    if pnl is not None:
        parts.append(f"PnL: {pnl:g}")
    parts.append(f"Wins: {wins}  Losses: {losses}")
    if equity is not None:
        parts.append(f"Equity: {equity:g}")
    return "\n".join(parts)

