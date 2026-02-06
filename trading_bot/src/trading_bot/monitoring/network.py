from __future__ import annotations

import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class NetworkRate:
    rx_bps: float
    tx_bps: float


class NetworkMonitor:
    def __init__(self) -> None:
        self._last = psutil.net_io_counters()
        self._last_t = time.time()

    def rate(self) -> NetworkRate:
        now = psutil.net_io_counters()
        t = time.time()
        dt = max(t - self._last_t, 1e-6)
        rx = (now.bytes_recv - self._last.bytes_recv) / dt
        tx = (now.bytes_sent - self._last.bytes_sent) / dt
        self._last = now
        self._last_t = t
        return NetworkRate(rx_bps=float(rx), tx_bps=float(tx))

