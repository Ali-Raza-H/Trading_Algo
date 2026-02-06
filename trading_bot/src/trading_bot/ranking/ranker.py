from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
import pandas as pd

from trading_bot.connectors.base import BrokerConnector, Quote, SymbolMeta
from trading_bot.core.timeframes import timeframe_seconds
from trading_bot.data.candles import returns as candle_returns
from trading_bot.data.pipeline import CandleBundle, DataPipeline
from trading_bot.ranking.correlation import greedy_correlation_filter
from trading_bot.ranking.normalizer import robust_minmax
from trading_bot.ranking.scorer import SymbolScore, compute_score


@dataclass(frozen=True)
class RankedSymbol:
    symbol: str
    score: float
    components: dict[str, float]
    raw: dict[str, Any]
    reasons: list[str]


@dataclass(frozen=True)
class RankOutput:
    ranked: list[RankedSymbol]
    selected: list[RankedSymbol]
    bundles: dict[str, CandleBundle]
    excluded: dict[str, str]


class Ranker:
    def __init__(
        self,
        *,
        connector: BrokerConnector,
        pipeline: DataPipeline,
        ranking_config: Any,
        timeframe: str,
    ) -> None:
        self.connector = connector
        self.pipeline = pipeline
        self.cfg = ranking_config
        self.timeframe = timeframe
        self._log = logging.getLogger("trading_bot.ranker")

    def rank(self, symbols: list[str], symbol_meta: dict[str, SymbolMeta]) -> RankOutput:
        bundles: dict[str, CandleBundle] = {}
        candidates: list[str] = []
        excluded: dict[str, str] = {}

        # First pass: fetch candles and quotes + filter
        quotes: dict[str, Quote] = {}
        raw_feats: dict[str, dict[str, Any]] = {}

        max_spread_points = int(self.cfg.filters.max_spread_points)
        max_spread_to_atr = float(self.cfg.filters.max_spread_to_atr_ratio)
        market_open_required = bool(self.cfg.filters.market_open_required)

        now = datetime.now(timezone.utc)
        tick_stale_seconds = min(10 * 60, timeframe_seconds(self.timeframe))

        for sym in symbols:
            b = self.pipeline.fetch(sym)
            bundles[sym] = b
            if b.candles is None or b.candles.empty or len(b.candles) < int(self.cfg.min_bars_required):
                excluded[sym] = "not enough bars"
                continue
            sm = symbol_meta.get(sym)
            if sm and sm.trade_allowed is False:
                excluded[sym] = "trade not allowed"
                continue
            q = self.connector.get_quote(sym)
            if q is None:
                excluded[sym] = "no quote"
                continue
            if market_open_required:
                age = (now - q.time_utc).total_seconds()
                if age > tick_stale_seconds:
                    excluded[sym] = f"stale tick age={int(age)}s"
                    continue
            if q.spread_points > max_spread_points:
                excluded[sym] = f"spread {q.spread_points:.1f} > {max_spread_points}"
                continue
            feats = b.features
            atr14 = feats.get("atr14")
            close = feats.get("close")
            if atr14 is None or close is None or atr14 <= 0 or close <= 0:
                excluded[sym] = "invalid ATR/close"
                continue
            spread_to_atr = (q.ask - q.bid) / float(atr14) if atr14 else float("inf")
            if spread_to_atr > max_spread_to_atr:
                excluded[sym] = f"spread/ATR {spread_to_atr:.2f} > {max_spread_to_atr:.2f}"
                continue

            quotes[sym] = q
            raw_feats[sym] = {
                "atr14": float(atr14),
                "atr14_pct": float(feats.get("atr14_pct") or (atr14 / close)),
                "adx14": float(feats.get("adx14") or 0.0),
                "momentum": self._momentum(feats),
                "spread_points": float(q.spread_points),
                "spread_to_atr": float(spread_to_atr),
            }
            candidates.append(sym)

        if not candidates:
            return RankOutput(ranked=[], selected=[], bundles=bundles, excluded=excluded)

        # Normalize
        vol_arr = np.array([raw_feats[s]["atr14_pct"] for s in candidates], dtype=float)
        trend_arr = np.array([raw_feats[s]["adx14"] for s in candidates], dtype=float)
        mom_arr = np.array([raw_feats[s]["momentum"] for s in candidates], dtype=float)
        cost_arr = np.array([raw_feats[s]["spread_to_atr"] for s in candidates], dtype=float)

        vol_n = robust_minmax(vol_arr)
        trend_n = robust_minmax(trend_arr)
        mom_n = robust_minmax(mom_arr)
        cost_n = robust_minmax(cost_arr)

        weights = self.cfg.weights.model_dump()
        ranked: list[RankedSymbol] = []
        for i, sym in enumerate(candidates):
            raw = raw_feats[sym]
            reasons = self._reasons(raw)
            score_obj: SymbolScore = compute_score(
                normalized={
                    "volatility": float(vol_n[i]),
                    "trend": float(trend_n[i]),
                    "momentum": float(mom_n[i]),
                    "cost": float(cost_n[i]),
                },
                weights=weights,
                raw=raw,
                reasons=reasons,
                symbol=sym,
            )
            ranked.append(
                RankedSymbol(
                    symbol=sym,
                    score=score_obj.score,
                    components=score_obj.components,
                    raw=raw,
                    reasons=score_obj.reasons,
                )
            )

        ranked.sort(key=lambda r: r.score, reverse=True)

        selected = ranked
        if bool(self.cfg.correlation.enabled) and len(ranked) > 1:
            window = int(self.cfg.correlation.window_bars)
            max_abs_corr = float(self.cfg.correlation.max_abs_corr)
            returns_df = self._returns_matrix(bundles, [r.symbol for r in ranked], window)
            decision = greedy_correlation_filter(
                [r.symbol for r in ranked],
                returns_df,
                max_abs_corr=max_abs_corr,
                top_n=int(self.cfg.top_n),
            )
            selected_syms = set(decision.selected)
            excluded.update({k: f"correlation filter: {v}" for k, v in decision.excluded.items()})
            selected = [r for r in ranked if r.symbol in selected_syms]
            selected.sort(key=lambda r: decision.selected.index(r.symbol))
        else:
            selected = ranked[: int(self.cfg.top_n)]

        return RankOutput(ranked=ranked, selected=selected, bundles=bundles, excluded=excluded)

    def _momentum(self, feats: dict[str, Any]) -> float:
        # Prefer oscillator histogram magnitude relative to ATR.
        atr14 = feats.get("atr14") or 0.0
        hist = feats.get("tp_hist")
        if hist is not None and atr14:
            return float(abs(hist) / float(atr14))
        ret20 = feats.get("ret20")
        if ret20 is not None:
            return float(abs(ret20))
        return 0.0

    def _reasons(self, raw: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        if raw.get("adx14", 0.0) >= 25:
            reasons.append("strong trend (ADX)")
        if raw.get("spread_to_atr", 1.0) <= 0.10:
            reasons.append("low cost (spread/ATR)")
        if raw.get("atr14_pct", 0.0) >= 0.004:
            reasons.append("good volatility (ATR%)")
        if raw.get("momentum", 0.0) >= 0.5:
            reasons.append("good momentum")
        return reasons or ["meets filters"]

    def _returns_matrix(
        self, bundles: dict[str, CandleBundle], symbols: list[str], window: int
    ) -> pd.DataFrame:
        cols: dict[str, pd.Series] = {}
        for sym in symbols:
            df = bundles.get(sym).candles if sym in bundles else None
            if df is None or df.empty:
                continue
            r = candle_returns(df).tail(window)
            cols[sym] = r
        if not cols:
            return pd.DataFrame()
        return pd.DataFrame(cols).dropna(how="any")

