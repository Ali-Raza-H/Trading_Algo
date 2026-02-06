from __future__ import annotations

import numpy as np


def robust_minmax(values: np.ndarray) -> np.ndarray:
    """
    Robustly scale values to 0..1.

    - Clips using median ± 3*IQR
    - Then min-max scales the clipped range
    - Constant arrays map to 0.5
    """
    v = values.astype(float)
    finite = v[np.isfinite(v)]
    if finite.size == 0:
        return np.full_like(v, np.nan, dtype=float)
    med = float(np.median(finite))
    q1, q3 = np.quantile(finite, [0.25, 0.75])
    iqr = float(q3 - q1)
    if iqr <= 1e-12:
        mn = float(np.min(finite))
        mx = float(np.max(finite))
        if abs(mx - mn) <= 1e-12:
            return np.full_like(v, 0.5, dtype=float)
        return (v - mn) / (mx - mn)
    lo = med - 3.0 * iqr
    hi = med + 3.0 * iqr
    clipped = np.clip(v, lo, hi)
    mn = float(np.nanmin(clipped))
    mx = float(np.nanmax(clipped))
    if abs(mx - mn) <= 1e-12:
        return np.full_like(v, 0.5, dtype=float)
    return (clipped - mn) / (mx - mn)

