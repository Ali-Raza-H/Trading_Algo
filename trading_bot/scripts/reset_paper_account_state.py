from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from trading_bot.core.config import load_config


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="reset_paper_account_state")
    p.add_argument("--config", type=str, default="config/config.yaml")
    p.add_argument("--keep-logs", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    cfg = load_config(args.config, db_latest_settings_json=None)
    db_path = Path(cfg.persistence.db_path)
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if db_path.exists():
        backup = db_path.with_suffix(db_path.suffix + f".bak_{stamp}")
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(db_path), str(backup))
        print(f"Moved DB -> {backup}")
    else:
        print("DB not found; nothing to reset")

    if not args.keep_logs:
        log_dir = Path("./logs")
        if log_dir.exists():
            shutil.rmtree(log_dir)
            print("Removed ./logs")

    data_dir = db_path.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    print("Reset complete")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
