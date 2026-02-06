from __future__ import annotations

import time
from typing import Callable, TypeVar

from trading_bot.core.exceptions import BrokerDisconnectedError, RetryableBrokerError

T = TypeVar("T")


def call_with_retries(
    fn: Callable[[], T],
    *,
    max_attempts: int,
    backoff_seconds: list[float],
) -> T:
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except (RetryableBrokerError, BrokerDisconnectedError) as exc:
            last_exc = exc
            if attempt >= max_attempts:
                break
            delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)] if backoff_seconds else 1.0
            time.sleep(float(delay))
    assert last_exc is not None
    raise last_exc

