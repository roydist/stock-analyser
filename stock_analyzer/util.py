from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd


def tanh_score(value: float, scale: float) -> float:
    """Map a signed magnitude onto [-100, 100] with a soft cap."""
    if scale == 0 or not math.isfinite(value) or not math.isfinite(scale):
        return 0.0
    return float(np.tanh(value / scale) * 100.0)


def clip(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return float(min(hi, max(lo, value)))


def finite(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def weighted_mean(pairs: Iterable[tuple[float, float | None]]) -> float | None:
    """Weighted average that skips None values and renormalizes weights."""
    num = 0.0
    den = 0.0
    for weight, value in pairs:
        if value is None or not math.isfinite(value):
            continue
        num += weight * float(value)
        den += weight
    if den == 0:
        return None
    return num / den


def last_finite(series: pd.Series | None) -> float | None:
    if series is None or series.empty:
        return None
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[-1])


def linear_slope_pct(series: pd.Series) -> float | None:
    """Implied percent change over the series from a linear fit."""
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if len(cleaned) < 3:
        return None
    y = cleaned.to_numpy(dtype=float)
    if np.allclose(y, y[0]):
        return 0.0
    x = np.arange(len(y), dtype=float)
    slope = float(np.polyfit(x, y, 1)[0])
    mean = float(np.mean(np.abs(y)))
    if mean == 0:
        return None
    return (slope * (len(y) - 1) / mean)


def as_unit_ratio(value: float | None, *, percent_if_abs_gt: float = 3.0) -> float | None:
    """Normalize Yahoo fields that mix 0.15 and 15 (%)."""
    v = finite(value)
    if v is None:
        return None
    if abs(v) > percent_if_abs_gt:
        return v / 100.0
    return v


def debt_equity_ratio(value: float | None) -> float | None:
    """Yahoo debtToEquity is usually percent (e.g. 140 == 1.40x)."""
    v = finite(value)
    if v is None:
        return None
    if abs(v) > 5:
        return v / 100.0
    return v


def series_trend_label(values_newest_first: pd.Series, threshold: float = 0.08) -> str:
    cleaned = pd.to_numeric(values_newest_first, errors="coerce").dropna()
    if len(cleaned) < 2:
        return "unknown"
    chrono = cleaned.to_numpy(dtype=float)[::-1]
    rel = linear_slope_pct(pd.Series(chrono))
    if rel is None:
        return "unknown"
    if rel > threshold:
        return "improving"
    if rel < -threshold:
        return "deteriorating"
    return "stable"


def yoy_growth(values_newest_first: pd.Series) -> float | None:
    cleaned = pd.to_numeric(values_newest_first, errors="coerce").dropna()
    if len(cleaned) < 2:
        return None
    old = float(cleaned.iloc[1])
    new = float(cleaned.iloc[0])
    if old == 0:
        return None
    return new / old - 1.0


def cagr(values_newest_first: pd.Series) -> float | None:
    cleaned = pd.to_numeric(values_newest_first, errors="coerce").dropna()
    if len(cleaned) < 2:
        return None
    oldest = float(cleaned.iloc[-1])
    newest = float(cleaned.iloc[0])
    years = len(cleaned) - 1
    if oldest <= 0 or newest <= 0 or years <= 0:
        return None
    return float((newest / oldest) ** (1.0 / years) - 1.0)


def pick_row(df: pd.DataFrame | None, *candidates: str) -> pd.Series | None:
    if df is None or df.empty:
        return None
    lower_map = {str(idx).strip().lower(): idx for idx in df.index}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in lower_map:
            row = df.loc[lower_map[key]]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return row
    for candidate in candidates:
        key = candidate.strip().lower()
        for lk, orig in lower_map.items():
            if key in lk:
                row = df.loc[orig]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                return row
    return None


def fmt_pct(value: float | None, *, digits: int = 1, signed: bool = True) -> str:
    v = finite(value)
    if v is None:
        return "—"
    pct = v * 100.0
    if signed:
        return f"{pct:+.{digits}f}%"
    return f"{pct:.{digits}f}%"


def fmt_number(value: float | None, *, digits: int = 2) -> str:
    v = finite(value)
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def fmt_compact(value: float | None) -> str:
    v = finite(value)
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    av = abs(v)
    if av >= 1e12:
        return f"{sign}{av / 1e12:.2f}T"
    if av >= 1e9:
        return f"{sign}{av / 1e9:.2f}B"
    if av >= 1e6:
        return f"{sign}{av / 1e6:.2f}M"
    if av >= 1e3:
        return f"{sign}{av / 1e3:.2f}K"
    return f"{v:.2f}"


def fmt_score(value: float | None) -> str:
    v = finite(value)
    if v is None:
        return "—"
    return f"{v:+.0f}"
