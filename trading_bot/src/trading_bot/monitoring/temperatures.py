from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any


def _psutil_temperature() -> float | None:
    try:
        import psutil

        temps = psutil.sensors_temperatures(fahrenheit=False)
        if not temps:
            return None
        # pick the hottest reasonable value
        best: float | None = None
        for entries in temps.values():
            for e in entries:
                cur = getattr(e, "current", None)
                if cur is None:
                    continue
                cur = float(cur)
                if cur <= 0 or cur > 150:
                    continue
                best = cur if best is None else max(best, cur)
        return best
    except Exception:
        return None


_SENSORS_RE = re.compile(r"([+-]?\\d+\\.\\d+)°C")


def _sensors_temperature() -> float | None:
    try:
        p = subprocess.run(
            ["sensors"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if p.returncode != 0:
            return None
        vals: list[float] = []
        for line in p.stdout.splitlines():
            m = _SENSORS_RE.search(line)
            if not m:
                continue
            vals.append(float(m.group(1)))
        if not vals:
            return None
        return max(vals)
    except Exception:
        return None


def _sysfs_temperature() -> float | None:
    try:
        base = Path("/sys/class/thermal")
        if not base.exists():
            return None
        vals: list[float] = []
        for tz in base.glob("thermal_zone*/temp"):
            try:
                raw = tz.read_text(encoding="utf-8").strip()
                if not raw:
                    continue
                v = float(raw)
                if v > 1000:
                    v = v / 1000.0
                if 0 < v < 150:
                    vals.append(v)
            except Exception:
                continue
        return max(vals) if vals else None
    except Exception:
        return None


def best_temperature_c() -> float | None:
    """
    Best-effort temperature:
      1) psutil.sensors_temperatures()
      2) `sensors` (lm-sensors)
      3) /sys/class/thermal
      4) None
    """
    return _psutil_temperature() or _sensors_temperature() or _sysfs_temperature()

