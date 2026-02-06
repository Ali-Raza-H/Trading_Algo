from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

from trading_bot.connectors.mt5_connector import MT5Connector
from trading_bot.core.config import load_config
from trading_bot.data.pipeline import DataPipeline
from trading_bot.persistence.db import Database
from trading_bot.ranking.ranker import Ranker


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="doctor")
    p.add_argument("--config", type=str, default="config/config.yaml")
    p.add_argument("--bars", type=int, default=300)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    load_dotenv(override=False)

    missing = [k for k in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER") if not os.getenv(k)]
    if missing:
        print(f"[FAIL] Missing env vars: {', '.join(missing)}")
        return 2
    print("[OK] Env vars present")

    cfg = load_config(args.config, db_latest_settings_json=None)
    db = Database(Path(cfg.persistence.db_path))
    db.initialize()

    conn = MT5Connector.from_env(timezone=cfg.runtime.tzinfo())
    ai = conn.account_info()
    if ai:
        print(f"[OK] Account: login={ai.login} server={ai.server} mode={ai.trade_mode} equity={ai.equity}")
    else:
        print("[WARN] account_info unavailable")

    symbols = conn.discover_symbols()
    print(f"[OK] Discovered symbols: {len(symbols)}")
    counts = Counter([s.asset_class.value for s in symbols])
    for k, v in counts.most_common():
        print(f"  - {k}: {v}")

    # Candle fetch sanity
    preferred = list(cfg.universe.preferred_symbols)
    candidate = preferred[0] if preferred else (symbols[0].name if symbols else None)
    if not candidate:
        print("[FAIL] No symbols available")
        return 2

    df = conn.get_candles(candidate, cfg.runtime.timeframe, int(args.bars))
    if df.empty:
        print(f"[FAIL] Candle fetch empty for {candidate}")
        return 2
    print(f"[OK] Candle fetch for {candidate}: {len(df)} bars, last time_utc={df['time_utc'].iloc[-1]}")

    pipeline = DataPipeline(conn, timeframe=cfg.runtime.timeframe, warmup_bars=int(cfg.runtime.warmup_bars))
    ranker = Ranker(connector=conn, pipeline=pipeline, ranking_config=cfg.ranking, timeframe=cfg.runtime.timeframe)
    universe = [s.name for s in symbols][: int(cfg.universe.discovery_limits.max_symbols_total)]
    meta = {s.name: s for s in symbols}
    out = ranker.rank(universe, meta)
    print("[OK] Ranking pass")
    for i, r in enumerate(out.selected[: int(cfg.ranking.top_n)], start=1):
        print(f"  {i}. {r.symbol} score={r.score:.3f} reasons={'; '.join(r.reasons)}")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
