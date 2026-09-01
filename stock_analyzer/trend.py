"""Price-trend scoring from OHLCV history.

All functions here are pure: they take a DataFrame and return scores. No I/O.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_analyzer.config import PERIODS, TREND_WEIGHTS, PeriodConfig, score_label
from stock_analyzer.models import PeriodTrend, TrendComponents
from stock_analyzer.util import clip, last_finite, linear_slope_pct, tanh_score, weighted_mean


def add_indicators(history: pd.DataFrame, *, rsi_period: int = 14) -> pd.DataFrame:
    """Attach SMA/EMA/RSI/MACD columns used by scoring and charts."""
    if history.empty or "Close" not in history.columns:
        raise ValueError("history must include a Close column")
    out = history.copy()
    close = out["Close"].astype(float)
    out["SMA_10"] = close.rolling(10, min_periods=10).mean()
    out["SMA_20"] = close.rolling(20, min_periods=20).mean()
    out["SMA_50"] = close.rolling(50, min_periods=50).mean()
    out["SMA_100"] = close.rolling(100, min_periods=100).mean()
    out["SMA_200"] = close.rolling(200, min_periods=200).mean()
    out["EMA_12"] = close.ewm(span=12, adjust=False).mean()
    out["EMA_26"] = close.ewm(span=26, adjust=False).mean()
    out["MACD"] = out["EMA_12"] - out["EMA_26"]
    out["MACD_signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD_hist"] = out["MACD"] - out["MACD_signal"]
    out["RSI"] = _rsi_wilder(close, rsi_period)
    return out


def _rsi_wilder(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi = rsi.where(avg_loss != 0, 100.0)
    rsi = rsi.where(avg_gain != 0, 0.0)
    # When both are 0 (flat tape), RSI is undefined — treat as 50.
    both_zero = (avg_gain == 0) & (avg_loss == 0)
    rsi = rsi.where(~both_zero, 50.0)
    return rsi


def score_periods(history: pd.DataFrame, periods: list[str]) -> list[PeriodTrend]:
    indicated = add_indicators(history)
    return [score_period(indicated, PERIODS[p]) for p in periods]


def score_period(history: pd.DataFrame, config: PeriodConfig | str) -> PeriodTrend:
    if isinstance(config, str):
        config = PERIODS[config]
    if "RSI" not in history.columns:
        history = add_indicators(history)

    window = _slice_window(history, config.bars)
    close = window["Close"].astype(float)
    n = len(close)
    if n < 5:
        raise ValueError(f"Not enough bars to score period {config.key} ({n} rows).")

    total_return = float(close.iloc[-1] / close.iloc[0] - 1.0)
    return_score = tanh_score(total_return, config.return_scale)

    fast_col = f"SMA_{config.sma_fast}"
    slow_col = f"SMA_{config.sma_slow}"
    if fast_col not in window.columns:
        window = window.copy()
        window[fast_col] = close.rolling(config.sma_fast, min_periods=config.sma_fast).mean()
    if slow_col not in window.columns:
        window = window.copy()
        window[slow_col] = close.rolling(config.sma_slow, min_periods=config.sma_slow).mean()

    sma_fast = last_finite(window[fast_col])
    sma_slow = last_finite(window[slow_col])
    last_close = float(close.iloc[-1])
    ma_alignment_score, ma_stack, price_vs_fast = _ma_alignment(last_close, sma_fast, sma_slow)

    slope_pct = linear_slope_pct(window[fast_col])
    ma_slope_score = tanh_score(slope_pct, config.return_scale) if slope_pct is not None else None

    structure_score, structure_label = _structure(close)

    rsi = last_finite(window["RSI"]) if "RSI" in window.columns else None
    macd = last_finite(window["MACD"]) if "MACD" in window.columns else None
    macd_signal = last_finite(window["MACD_signal"]) if "MACD_signal" in window.columns else None
    macd_hist = last_finite(window["MACD_hist"]) if "MACD_hist" in window.columns else None
    momentum_score = _momentum_score(rsi, macd_hist, last_close)

    score = weighted_mean(
        [
            (TREND_WEIGHTS["return"], return_score),
            (TREND_WEIGHTS["ma_alignment"], ma_alignment_score),
            (TREND_WEIGHTS["ma_slope"], ma_slope_score),
            (TREND_WEIGHTS["structure"], structure_score),
            (TREND_WEIGHTS["momentum"], momentum_score),
        ]
    )
    if score is None:
        score = return_score
    score = clip(score)

    components = TrendComponents(
        total_return=total_return,
        return_score=return_score,
        sma_fast=sma_fast,
        sma_slow=sma_slow,
        sma_fast_period=config.sma_fast,
        sma_slow_period=config.sma_slow,
        price_vs_fast=price_vs_fast,
        ma_stack=ma_stack,
        sma_fast_slope_pct=slope_pct,
        ma_alignment_score=ma_alignment_score,
        ma_slope_score=ma_slope_score,
        structure_score=structure_score,
        structure_label=structure_label,
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        macd_hist=macd_hist,
        momentum_score=momentum_score,
        n_bars=n,
        start=str(window.index[0].date()) if hasattr(window.index[0], "date") else str(window.index[0]),
        end=str(window.index[-1].date()) if hasattr(window.index[-1], "date") else str(window.index[-1]),
        last_close=last_close,
    )
    return PeriodTrend(
        period=config.key,
        horizon=config.horizon,
        score=score,
        label=score_label(score),
        components=components,
    )


def _slice_window(history: pd.DataFrame, bars: int) -> pd.DataFrame:
    if len(history) <= bars:
        return history
    return history.iloc[-bars:]


def _ma_alignment(
    close: float,
    sma_fast: float | None,
    sma_slow: float | None,
) -> tuple[float | None, str | None, str | None]:
    price_vs_fast = None
    if sma_fast is not None:
        price_vs_fast = "above" if close >= sma_fast else "below"

    if sma_fast is None and sma_slow is None:
        return None, None, price_vs_fast
    if sma_fast is None or sma_slow is None:
        # Only one MA: use price vs that MA.
        ma = sma_fast if sma_fast is not None else sma_slow
        assert ma is not None
        score = 70.0 if close >= ma else -70.0
        stack = "bullish" if score > 0 else "bearish"
        return score, stack, price_vs_fast

    if close >= sma_fast >= sma_slow:
        return 100.0, "bullish", price_vs_fast
    if close <= sma_fast <= sma_slow:
        return -100.0, "bearish", price_vs_fast
    if close >= sma_fast:
        return 40.0, "mixed", price_vs_fast
    if close <= sma_fast:
        return -40.0, "mixed", price_vs_fast
    return 0.0, "mixed", price_vs_fast


def find_swings(close: pd.Series, order: int = 5) -> tuple[list[float], list[float]]:
    """Return peak and trough prices using a symmetric local-extrema window."""
    values = close.to_numpy(dtype=float)
    n = len(values)
    if n < order * 2 + 1:
        return [], []
    peaks: list[float] = []
    troughs: list[float] = []
    for i in range(order, n - order):
        window = values[i - order : i + order + 1]
        v = values[i]
        if v >= window.max() and np.sum(window == v) == 1:
            peaks.append(float(v))
        elif v <= window.min() and np.sum(window == v) == 1:
            troughs.append(float(v))
    return peaks, troughs


def _structure(close: pd.Series) -> tuple[float, str]:
    n = len(close)
    order = max(3, min(8, n // 12))
    peaks, troughs = find_swings(close, order=order)

    hh = hl = lh = ll = False
    if len(peaks) >= 2:
        hh = peaks[-1] > peaks[-2]
        lh = peaks[-1] < peaks[-2]
    if len(troughs) >= 2:
        hl = troughs[-1] > troughs[-2]
        ll = troughs[-1] < troughs[-2]

    if hh and hl:
        return 100.0, "higher highs & higher lows"
    if lh and ll:
        return -100.0, "lower highs & lower lows"
    if hh and ll:
        return 20.0, "higher highs but lower lows (expanding range)"
    if lh and hl:
        return -20.0, "lower highs but higher lows (contracting range)"
    if hh:
        return 50.0, "higher highs"
    if hl:
        return 50.0, "higher lows"
    if lh:
        return -50.0, "lower highs"
    if ll:
        return -50.0, "lower lows"

    # Few identifiable swings: infer from monotonicity of the window.
    total_return = float(close.iloc[-1] / close.iloc[0] - 1.0)
    if total_return > 0.04:
        return 80.0, "mostly advancing (few swings)"
    if total_return < -0.04:
        return -80.0, "mostly declining (few swings)"
    return 0.0, "no clear swing structure"


def _momentum_score(rsi: float | None, macd_hist: float | None, last_close: float) -> float | None:
    parts: list[tuple[float, float | None]] = []
    if rsi is not None:
        # Center RSI at 50; compress so 70/30 map to roughly +/-40, not a full 100.
        parts.append((0.4, tanh_score(rsi - 50.0, 25.0)))
    if macd_hist is not None and last_close:
        parts.append((0.6, tanh_score(macd_hist / last_close, 0.01)))
    return weighted_mean(parts)
