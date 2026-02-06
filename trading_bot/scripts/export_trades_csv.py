from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from trading_bot.core.config import load_config
from trading_bot.persistence.db import Database


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="export_trades_csv")
    p.add_argument("--config", type=str, default="config/config.yaml")
    p.add_argument("--out", type=str, default="trades.csv")
    p.add_argument("--limit", type=int, default=5000)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    cfg = load_config(args.config, db_latest_settings_json=None)
    db = Database(Path(cfg.persistence.db_path))
    db.initialize()
    rows = db.trade_repo().list_recent(limit=int(args.limit))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            return 0
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
