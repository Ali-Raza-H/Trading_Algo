from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import psutil


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_pct: float
    ram_pct: float
    disk_pct: float
    uptime_seconds: float
    pid: int


class ResourceMonitor:
    def __init__(self) -> None:
        self._proc = psutil.Process(os.getpid())
        self._start_time = time.time()

    def snapshot(self) -> ResourceSnapshot:
        cpu = float(psutil.cpu_percent(interval=None))
        mem = psutil.virtual_memory()
        ram = float(mem.percent)
        disk = psutil.disk_usage(".")
        disk_pct = float(disk.percent)
        uptime = time.time() - self._start_time
        return ResourceSnapshot(
            cpu_pct=cpu,
            ram_pct=ram,
            disk_pct=disk_pct,
            uptime_seconds=float(uptime),
            pid=int(self._proc.pid),
        )

