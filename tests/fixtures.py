"""Shared synthetic OHLCV and fundamentals fixtures (no network)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from stock_analyzer.config import PERIODS, score_label
from stock_analyzer.data import FundamentalsBundle
from stock_analyzer.models import PeriodTrend, TrendComponents


def make_ohlcv(
    n: int = 400,
    *,
    start: float = 100.0,
    drift: float = 0.001,
    vol: float = 0.0,
    seed: int = 0,
    start_date: str = "2018-01-02",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    shocks = np.zeros(n) if vol == 0 else vol * rng.standard_normal(n)
    rets = drift + shocks
    close = start * np.exp(np.cumsum(rets))
    idx = pd.bdate_range(start_date, periods=n)
    open_ = np.concatenate([[start], close[:-1]])
    return pd.DataFrame(
        {
            "Open": open_,
            "High": close * 1.004,
            "Low": close * 0.996,
            "Close": close,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def make_sine_ohlcv(n: int = 400, *, center: float = 100.0, amplitude: float = 3.0) -> pd.DataFrame:
    idx = pd.bdate_range("2018-01-02", periods=n)
    x = np.linspace(0, 8 * np.pi, n)
    close = center + amplitude * np.sin(x)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close + 0.2,
            "Low": close - 0.2,
            "Close": close,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def interpolate_swings(points: list[float], bars_each: int = 12) -> pd.DataFrame:
    series: list[float] = []
    for a, b in zip(points[:-1], points[1:]):
        series.extend(np.linspace(a, b, bars_each, endpoint=False).tolist())
    series.append(float(points[-1]))
    n = len(series)
    idx = pd.bdate_range("2020-01-02", periods=n)
    close = np.asarray(series, dtype=float)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.002,
            "Low": close * 0.998,
            "Close": close,
            "Volume": np.full(n, 1_000_000.0),
        },
        index=idx,
    )


def strong_company_bundle() -> FundamentalsBundle:
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
    income = pd.DataFrame(
        {
            cols[0]: [120.0, 24.0, 60.0, 36.0, 4.0],
            cols[1]: [100.0, 18.0, 48.0, 28.0, 3.0],
            cols[2]: [80.0, 12.0, 36.0, 20.0, 2.0],
        },
        index=["Total Revenue", "Net Income", "Gross Profit", "Operating Income", "Diluted EPS"],
    )
    cash = pd.DataFrame(
        {
            cols[0]: [20.0, 28.0, -8.0],
            cols[1]: [15.0, 22.0, -7.0],
            cols[2]: [10.0, 16.0, -6.0],
        },
        index=["Free Cash Flow", "Operating Cash Flow", "Capital Expenditure"],
    )
    info = {
        "longName": "Acme Growth Corp",
        "sector": "Technology",
        "industry": "Software",
        "trailingPE": 22.0,
        "forwardPE": 18.0,
        "priceToSalesTrailing12Months": 5.0,
        "priceToBook": 6.0,
        "enterpriseToEbitda": 14.0,
        "grossMargins": 0.50,
        "operatingMargins": 0.30,
        "profitMargins": 0.20,
        "returnOnEquity": 0.28,
        "returnOnAssets": 0.12,
        "debtToEquity": 40.0,  # Yahoo-style percent → 0.40x
        "freeCashflow": 20.0,
        "revenueGrowth": 0.20,
        "earningsGrowth": 0.30,
        "currency": "USD",
    }
    return FundamentalsBundle(info=info, income_annual=income, cashflow_annual=cash)


def weak_company_bundle() -> FundamentalsBundle:
    cols = [pd.Timestamp("2024-12-31"), pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
    income = pd.DataFrame(
        {
            cols[0]: [70.0, -8.0, 10.0, -4.0, -1.5],
            cols[1]: [90.0, 2.0, 18.0, 4.0, 0.3],
            cols[2]: [100.0, 8.0, 25.0, 10.0, 1.2],
        },
        index=["Total Revenue", "Net Income", "Gross Profit", "Operating Income", "Diluted EPS"],
    )
    cash = pd.DataFrame(
        {
            cols[0]: [-12.0],
            cols[1]: [-4.0],
            cols[2]: [3.0],
        },
        index=["Free Cash Flow"],
    )
    info = {
        "longName": "Fading Co",
        "sector": "Consumer Cyclical",
        "trailingPE": -5.0,
        "profitMargins": -0.11,
        "operatingMargins": -0.06,
        "grossMargins": 0.14,
        "returnOnEquity": -0.20,
        "debtToEquity": 320.0,
        "revenueGrowth": -0.22,
        "earningsGrowth": -1.0,
    }
    return FundamentalsBundle(info=info, income_annual=income, cashflow_annual=cash)


def stub_trend(period: str, score: float, *, rsi: float = 55.0, structure: str = "higher highs & higher lows") -> PeriodTrend:
    cfg = PERIODS[period]
    components = TrendComponents(
        total_return=score / 200.0,
        return_score=score,
        sma_fast=100.0,
        sma_slow=95.0,
        sma_fast_period=cfg.sma_fast,
        sma_slow_period=cfg.sma_slow,
        price_vs_fast="above" if score >= 0 else "below",
        ma_stack="bullish" if score >= 20 else "bearish" if score <= -20 else "mixed",
        sma_fast_slope_pct=score / 200.0,
        ma_alignment_score=score,
        ma_slope_score=score,
        structure_score=score,
        structure_label=structure,
        rsi=rsi,
        macd=1.0 if score >= 0 else -1.0,
        macd_signal=0.5 if score >= 0 else -0.5,
        macd_hist=0.5 if score >= 0 else -0.5,
        momentum_score=score * 0.5,
        n_bars=cfg.bars,
        start="2024-01-02",
        end="2024-12-31",
        last_close=100.0,
    )
    return PeriodTrend(
        period=period,
        horizon=cfg.horizon,
        score=score,
        label=score_label(score),
        components=components,
    )
