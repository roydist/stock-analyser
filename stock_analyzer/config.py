"""Defaults, period definitions, and the documented scoring method."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_TICKERS = ("AAPL", "TSLA", "HD", "ETN", "VRT", "VST", "NAGE")
DEFAULT_PERIODS = ("1mo", "3mo", "6mo", "1y", "5y")


@dataclass(frozen=True)
class PeriodConfig:
    key: str
    horizon: str  # short | medium | long
    bars: int  # nominal trading days in the window
    sma_fast: int
    sma_slow: int
    # Absolute total return that maps near +/-100 on the return component (via tanh).
    return_scale: float


PERIODS: dict[str, PeriodConfig] = {
    "1mo": PeriodConfig("1mo", "short", 21, 10, 20, 0.12),
    "3mo": PeriodConfig("3mo", "short", 63, 20, 50, 0.20),
    "6mo": PeriodConfig("6mo", "medium", 126, 20, 50, 0.28),
    "1y": PeriodConfig("1y", "medium", 252, 50, 100, 0.35),
    "2y": PeriodConfig("2y", "long", 504, 50, 200, 0.70),
    "5y": PeriodConfig("5y", "long", 1260, 50, 200, 1.20),
    "10y": PeriodConfig("10y", "long", 2520, 50, 200, 1.80),
}

HORIZON_PERIODS = {
    "short": ("1mo", "3mo"),
    "medium": ("6mo", "1y"),
    "long": ("2y", "5y", "10y"),
}

# How much extra daily history to request so SMAs/RSI/MACD are defined
# at the start of the longest requested window.
INDICATOR_LOOKBACK_BARS = 250

TREND_WEIGHTS = {
    "return": 0.30,
    "ma_alignment": 0.25,
    "ma_slope": 0.20,
    "structure": 0.15,
    "momentum": 0.10,
}

SCORE_LABELS = (
    (50, "Strong uptrend"),
    (20, "Uptrend"),
    (-20, "Sideways / mixed"),
    (-50, "Downtrend"),
    (float("-inf"), "Strong downtrend"),
)

METHOD_SUMMARY = """
Trend score method (per ticker, per period)
-------------------------------------------
Each period is scored from -100 (strong downtrend) to +100 (strong uptrend).
The headline score is a weighted blend of five components (weights renormalized
if a component cannot be computed, e.g. a new listing with no SMA200):

  1. Return (30%) — total close-to-close return over the window, compressed with
     tanh(return / period_scale) so a typical "strong" move for that horizon sits
     near +/-100. Scales: 1mo ~12%, 3mo ~20%, 6mo ~28%, 1y ~35%, 5y ~120%.
  2. MA alignment (25%) — end-of-window close vs SMA_fast vs SMA_slow.
     Price > fast > slow is fully bullish; the inverse is fully bearish.
  3. MA slope (20%) — linear-regression slope of the fast SMA across the window,
     expressed as implied percent change, then tanh-scaled like returns.
  4. Market structure (15%) — swing highs/lows (local extrema). Higher-highs and
     higher-lows score bullish; lower-highs and lower-lows score bearish.
     A nearly monotonic move is treated as implicit structure in that direction.
  5. Momentum (10%) — supporting context only: MACD histogram sign/magnitude and
     RSI(14). RSI>70 is tagged overbought; RSI<30 oversold. This component cannot
     by itself produce a "strong" label.

Horizons: 1mo/3mo = short-term, 6mo/1y = medium-term, 2y/5y/10y = long-term.
Short, medium, and long scores are allowed to disagree; the report calls that out.

Fundamentals
------------
Pulled from Yahoo Finance via yfinance (no API key): revenue and EPS/net-income
trend, gross/operating/profit margins, PE/PS/PB and EV/EBITDA when present,
debt/equity, free cash flow, ROE/ROA. Quality is a 0–100 heuristic (growth,
profitability, leverage, cash generation, trend of earnings and margins) — not
a valuation target or buy/sell rating.

Synthesis
---------
A short qualitative paragraph compares price trend vs fundamental direction,
e.g. "uptrend with improving margins" vs "price rising while earnings deteriorate".
""".strip()


def parse_periods(raw: str) -> list[str]:
    parts = [p.strip().lower() for p in raw.replace(" ", ",").split(",") if p.strip()]
    if not parts:
        raise ValueError("At least one period is required.")
    unknown = [p for p in parts if p not in PERIODS]
    if unknown:
        supported = ", ".join(PERIODS)
        raise ValueError(f"Unknown period(s): {', '.join(unknown)}. Supported: {supported}")
    return parts


def parse_tickers(raw: str | None) -> list[str]:
    if not raw:
        return list(DEFAULT_TICKERS)
    parts = [p.strip().upper() for p in raw.replace(",", " ").split() if p.strip()]
    if not parts:
        return list(DEFAULT_TICKERS)
    return parts


def yfinance_fetch_period(requested: list[str]) -> str:
    """Choose a yfinance history period that covers the longest window + lookback."""
    max_bars = max(PERIODS[p].bars for p in requested)
    needed = max_bars + INDICATOR_LOOKBACK_BARS
    if needed <= 280:
        return "1y"
    if needed <= 560:
        return "2y"
    if needed <= 1510:
        return "5y"
    if needed <= 2800:
        return "10y"
    return "max"


def score_label(score: float) -> str:
    for threshold, label in SCORE_LABELS:
        if score >= threshold:
            return label
    return "Sideways / mixed"
