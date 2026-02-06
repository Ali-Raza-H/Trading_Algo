from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CorrelationDecision:
    selected: list[str]
    excluded: dict[str, str]  # symbol -> reason


def greedy_correlation_filter(
    ranked_symbols: list[str],
    returns_df: pd.DataFrame,
    *,
    max_abs_corr: float,
    top_n: int,
) -> CorrelationDecision:
    if returns_df.empty or len(ranked_symbols) <= 1:
        return CorrelationDecision(selected=ranked_symbols[:top_n], excluded={})

    corr = returns_df[ranked_symbols].corr().fillna(0.0)
    selected: list[str] = []
    excluded: dict[str, str] = {}

    for sym in ranked_symbols:
        if len(selected) >= top_n:
            break
        ok = True
        for s2 in selected:
            c = float(corr.loc[sym, s2])
            if abs(c) > max_abs_corr:
                excluded[sym] = f"|corr({sym},{s2})|={abs(c):.2f} > {max_abs_corr:.2f}"
                ok = False
                break
        if ok:
            selected.append(sym)

    # If not enough, fill with remaining regardless (still prefer having top_n)
    if len(selected) < top_n:
        for sym in ranked_symbols:
            if len(selected) >= top_n:
                break
            if sym in selected:
                continue
            selected.append(sym)

    return CorrelationDecision(selected=selected, excluded=excluded)

