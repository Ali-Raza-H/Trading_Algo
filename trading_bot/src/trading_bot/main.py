from __future__ import annotations

import argparse
import logging
import signal
import sys
from pathlib import Path

from trading_bot.core.config import load_config
from trading_bot.core.utils import platform_summary, setup_logging
from trading_bot.engine.bot_engine import BotEngine
from trading_bot.persistence.db import Database
from trading_bot.ui.app import TradingBotApp


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="trading-bot")
    p.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to config.yaml",
    )
    p.add_argument("--no-ui", action="store_true", help="Run headless (no TUI)")
    p.add_argument("--log-level", type=str, default="INFO")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    setup_logging("./logs", level=args.log_level)
    log = logging.getLogger("trading_bot")
    log.info("starting", extra={"platform": dict(platform_summary())})

    # Load config file first to discover db_path, then merge latest settings snapshot.
    base_config = load_config(args.config, db_latest_settings_json=None)
    db = Database(Path(base_config.persistence.db_path))
    db.initialize()
    latest_settings = db.settings_repo().get_latest_snapshot_json()

    config = load_config(args.config, db_latest_settings_json=latest_settings)
    if Path(config.persistence.db_path) != db.path:
        db = Database(Path(config.persistence.db_path))
        db.initialize()

    engine = BotEngine(config=config, db=db)

    stop_requested = False

    def _handle_sig(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        if stop_requested:
            return
        stop_requested = True
        log.warning("shutdown requested", extra={"signal": signum})
        engine.request_stop()

    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    if config.ui.enabled and not args.no_ui:
        app = TradingBotApp(engine=engine, db=db, config=config)
        app.run()
    else:
        engine.start()
        engine.join()

    log.info("stopped")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
