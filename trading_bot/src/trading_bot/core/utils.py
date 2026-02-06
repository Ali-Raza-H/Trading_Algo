from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import platform
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Mapping


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def safe_json_dumps(obj: Any) -> str:
    def _default(o: Any) -> Any:
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        if isinstance(o, datetime):
            return iso_utc(o)
        if hasattr(o, "model_dump"):
            return o.model_dump()
        if isinstance(o, Path):
            return str(o)
        return str(o)

    return json.dumps(obj, default=_default, ensure_ascii=False, separators=(",", ":"))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Custom extras
        for key, value in record.__dict__.items():
            if key.startswith("_"):
                continue
            if key in {
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
            }:
                continue
            payload[key] = value
        return safe_json_dumps(payload)


def setup_logging(log_dir: str, level: str = "INFO") -> None:
    ensure_dir(log_dir)
    level_num = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level_num)
    root.handlers.clear()

    # Console (human)
    console = logging.StreamHandler(stream=sys.stdout)
    console.setLevel(level_num)
    console.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(console)

    # Rotating text log
    text_path = Path(log_dir) / "bot.log"
    text_handler = RotatingFileHandler(
        text_path, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    text_handler.setLevel(level_num)
    text_handler.setFormatter(console.formatter)
    root.addHandler(text_handler)

    # Rotating JSONL log
    jsonl_path = Path(log_dir) / "bot.jsonl"
    json_handler = RotatingFileHandler(
        jsonl_path, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
    )
    json_handler.setLevel(level_num)
    json_handler.setFormatter(JsonFormatter())
    root.addHandler(json_handler)

    # Reduce noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def platform_summary() -> Mapping[str, Any]:
    return {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
    }

