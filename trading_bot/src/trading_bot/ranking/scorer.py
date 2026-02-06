from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class SymbolScoreInput:
    symbol: str
    atr14: float
    close: float
    adx14: float
    momentum: float
    spread_points: float
    spread_to_atr: float


@dataclass(frozen=True)
class SymbolScore:
    symbol: str
    score: float
    components: dict[str, float]
    raw: dict[str, Any]
    reasons: list[str]


def compute_score(
    *,
    normalized: dict[str, float],
    weights: dict[str, float],
    raw: dict[str, Any],
    reasons: list[str],
    symbol: str,
) -> SymbolScore:
    vol = float(normalized.get("volatility", 0.0))
    trend = float(normalized.get("trend", 0.0))
    mom = float(normalized.get("momentum", 0.0))
    cost_norm = float(normalized.get("cost", 1.0))
    cost_score = 1.0 - cost_norm

    wv = float(weights.get("volatility", 0.0))
    wt = float(weights.get("trend", 0.0))
    wm = float(weights.get("momentum", 0.0))
    wc = float(weights.get("cost", 0.0))
    total_w = max(wv + wt + wm + wc, 1e-12)

    score = (wv * vol + wt * trend + wm * mom + wc * cost_score) / total_w
    score = float(np.clip(score, 0.0, 1.0))
    return SymbolScore(
        symbol=symbol,
        score=score,
        components={
            "volatility": vol,
            "trend": trend,
            "momentum": mom,
            "cost": cost_score,
        },
        raw=raw,
        reasons=reasons,
    )

