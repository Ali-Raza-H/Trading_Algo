from __future__ import annotations

from trading_bot.execution.idempotency import make_idempotency_key


def test_idempotency_stable() -> None:
    k1 = make_idempotency_key(
        symbol="EURUSD",
        timeframe="H1",
        candle_close_time_utc="2026-01-01T00:00:00+00:00",
        strategy="two_pole_momentum",
        side="long",
    )
    k2 = make_idempotency_key(
        symbol="EURUSD",
        timeframe="H1",
        candle_close_time_utc="2026-01-01T00:00:00+00:00",
        strategy="two_pole_momentum",
        side="long",
    )
    assert k1 == k2


def test_idempotency_changes_with_side() -> None:
    k1 = make_idempotency_key(
        symbol="EURUSD",
        timeframe="H1",
        candle_close_time_utc="2026-01-01T00:00:00+00:00",
        strategy="two_pole_momentum",
        side="long",
    )
    k2 = make_idempotency_key(
        symbol="EURUSD",
        timeframe="H1",
        candle_close_time_utc="2026-01-01T00:00:00+00:00",
        strategy="two_pole_momentum",
        side="short",
    )
    assert k1 != k2

