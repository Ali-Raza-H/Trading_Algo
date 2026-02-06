from __future__ import annotations

from datetime import timedelta


def fmt_pct(v: float | None) -> str:
    if v is None:
        return "N/A"
    return f"{v:.1f}%"


def fmt_float(v: float | None, *, ndp: int = 2) -> str:
    if v is None:
        return "N/A"
    return f"{v:.{ndp}f}"


def fmt_int(v: int | None) -> str:
    if v is None:
        return "N/A"
    return str(int(v))


def fmt_bps(v: float | None) -> str:
    if v is None:
        return "N/A"
    # bytes per second
    x = float(v)
    if x < 1024:
        return f"{x:.0f} B/s"
    if x < 1024**2:
        return f"{x/1024:.1f} KB/s"
    return f"{x/(1024**2):.1f} MB/s"


def fmt_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    td = timedelta(seconds=int(seconds))
    s = str(td)
    return s

