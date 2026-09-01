from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TrendComponents:
    total_return: float
    return_score: float
    sma_fast: float | None
    sma_slow: float | None
    sma_fast_period: int
    sma_slow_period: int
    price_vs_fast: str | None  # above | below | None
    ma_stack: str | None  # bullish | bearish | mixed | None
    sma_fast_slope_pct: float | None
    ma_alignment_score: float | None
    ma_slope_score: float | None
    structure_score: float | None
    structure_label: str
    rsi: float | None
    macd: float | None
    macd_signal: float | None
    macd_hist: float | None
    momentum_score: float | None
    n_bars: int
    start: str | None
    end: str | None
    last_close: float | None


@dataclass
class PeriodTrend:
    period: str
    horizon: str
    score: float
    label: str
    components: TrendComponents


@dataclass
class HorizonView:
    short: float | None
    medium: float | None
    long: float | None
    short_label: str | None
    medium_label: str | None
    long_label: str | None
    agreement: str  # aligned | mixed | conflicting | single-horizon
    agreement_note: str


@dataclass
class FundamentalsSnapshot:
    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    pe_trailing: float | None = None
    pe_forward: float | None = None
    ps: float | None = None
    pb: float | None = None
    ev_ebitda: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    roe: float | None = None
    roa: float | None = None
    revenue_growth_yoy: float | None = None
    revenue_cagr: float | None = None
    earnings_growth_yoy: float | None = None
    eps_trend: str = "unknown"
    margin_trend: str = "unknown"
    debt_to_equity: float | None = None
    free_cash_flow: float | None = None
    fcf_trend: str = "unknown"
    quality_score: float | None = None
    quality_label: str = "Unknown"
    notes: list[str] = field(default_factory=list)


@dataclass
class TickerAnalysis:
    ticker: str
    error: str | None = None
    fundamentals: FundamentalsSnapshot | None = None
    trends: list[PeriodTrend] = field(default_factory=list)
    horizons: HorizonView | None = None
    headline: str = ""
    synthesis: str = ""

    def trend_by_period(self) -> dict[str, PeriodTrend]:
        return {t.period: t for t in self.trends}


@dataclass
class AnalysisReport:
    tickers: list[TickerAnalysis]
    periods: list[str]
    generated_at: str
    method_summary: str
    disclaimer: str
    source: str = "Yahoo Finance via yfinance (no API key)"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
