"""Fundamental snapshot and quality heuristic from Yahoo-style statements."""

from __future__ import annotations

from typing import Any

import pandas as pd

from stock_analyzer.data import FundamentalsBundle
from stock_analyzer.models import FundamentalsSnapshot
from stock_analyzer.util import (
    as_unit_ratio,
    cagr,
    debt_equity_ratio,
    finite,
    pick_row,
    series_trend_label,
    tanh_score,
    weighted_mean,
    yoy_growth,
)


def analyze_fundamentals(ticker: str, bundle: FundamentalsBundle) -> FundamentalsSnapshot:
    info = bundle.info or {}
    income = bundle.income_annual
    cashflow = bundle.cashflow_annual

    revenue = pick_row(income, "Total Revenue", "Operating Revenue", "Revenue")
    net_income = pick_row(
        income,
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income Continuous Operations",
    )
    gross_profit = pick_row(income, "Gross Profit")
    operating_income = pick_row(income, "Operating Income", "EBIT")
    diluted_eps = pick_row(income, "Diluted EPS", "Basic EPS", "Diluted EPS Other Gains Losses")
    fcf = pick_row(cashflow, "Free Cash Flow")
    if fcf is None:
        ocf = pick_row(
            cashflow,
            "Operating Cash Flow",
            "Cash Flow From Continuing Operating Activities",
        )
        capex = pick_row(cashflow, "Capital Expenditure", "Purchase Of PPE")
        if ocf is not None and capex is not None:
            fcf = pd.to_numeric(ocf, errors="coerce") + pd.to_numeric(capex, errors="coerce")

    revenue_yoy = yoy_growth(revenue) if revenue is not None else as_unit_ratio(info.get("revenueGrowth"))
    revenue_cagr = cagr(revenue) if revenue is not None else None
    earnings_yoy = (
        yoy_growth(diluted_eps)
        if diluted_eps is not None
        else yoy_growth(net_income)
        if net_income is not None
        else as_unit_ratio(info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth"))
    )

    eps_source = diluted_eps if diluted_eps is not None else net_income
    eps_trend = series_trend_label(eps_source) if eps_source is not None else "unknown"

    margin_series = _margin_series(gross_profit, operating_income, revenue)
    margin_trend = series_trend_label(margin_series, threshold=0.05) if margin_series is not None else "unknown"

    fcf_trend = series_trend_label(fcf) if fcf is not None else "unknown"
    latest_fcf = _latest(fcf)

    snap = FundamentalsSnapshot(
        ticker=ticker.upper(),
        name=_info_str(info, "longName", "shortName"),
        sector=_info_str(info, "sector"),
        industry=_info_str(info, "industry"),
        pe_trailing=finite(info.get("trailingPE")),
        pe_forward=finite(info.get("forwardPE")),
        ps=finite(info.get("priceToSalesTrailing12Months")),
        pb=finite(info.get("priceToBook")),
        ev_ebitda=finite(info.get("enterpriseToEbitda")),
        gross_margin=as_unit_ratio(info.get("grossMargins")),
        operating_margin=as_unit_ratio(info.get("operatingMargins")),
        profit_margin=as_unit_ratio(info.get("profitMargins")),
        roe=as_unit_ratio(info.get("returnOnEquity")),
        roa=as_unit_ratio(info.get("returnOnAssets")),
        revenue_growth_yoy=revenue_yoy,
        revenue_cagr=revenue_cagr,
        earnings_growth_yoy=earnings_yoy,
        eps_trend=eps_trend,
        margin_trend=margin_trend,
        debt_to_equity=debt_equity_ratio(info.get("debtToEquity")),
        free_cash_flow=latest_fcf,
        fcf_trend=fcf_trend,
    )
    if snap.gross_margin is None:
        snap.gross_margin = _latest_margin(gross_profit, revenue)
    if snap.operating_margin is None:
        snap.operating_margin = _latest_margin(operating_income, revenue)
    if snap.profit_margin is None:
        snap.profit_margin = _latest_margin(net_income, revenue)

    snap.notes = _notes(snap, info)
    snap.quality_score, snap.quality_label = quality_score(snap)
    return snap


def quality_score(snap: FundamentalsSnapshot) -> tuple[float | None, str]:
    """0–100 fundamental health heuristic. Missing inputs are skipped."""
    growth = None
    g = snap.revenue_growth_yoy if snap.revenue_growth_yoy is not None else snap.revenue_cagr
    if g is not None:
        growth = 50.0 + tanh_score(g, 0.25) / 2.0  # ~0% -> 50, +25% -> ~85

    profitability = weighted_mean(
        [
            (0.4, _margin_to_score(snap.operating_margin, good=0.15)),
            (0.3, _margin_to_score(snap.profit_margin, good=0.10)),
            (0.3, _margin_to_score(snap.roe, good=0.15)),
        ]
    )

    leverage = None
    if snap.debt_to_equity is not None:
        # 0x -> ~90, 1x -> ~70, 2x -> ~50, 4x+ -> weak
        leverage = 90.0 - min(80.0, snap.debt_to_equity * 20.0)

    cash = None
    if snap.free_cash_flow is not None:
        cash = 75.0 if snap.free_cash_flow > 0 else 25.0
        if snap.fcf_trend == "improving" and cash >= 75:
            cash = 85.0
        if snap.fcf_trend == "deteriorating":
            cash -= 15.0

    trend_adj = None
    if snap.eps_trend != "unknown" or snap.margin_trend != "unknown":
        trend_adj = 50.0
        if snap.eps_trend == "improving":
            trend_adj += 20.0
        elif snap.eps_trend == "deteriorating":
            trend_adj -= 25.0
        if snap.margin_trend == "improving":
            trend_adj += 10.0
        elif snap.margin_trend == "deteriorating":
            trend_adj -= 15.0
        trend_adj = max(0.0, min(100.0, trend_adj))

    score = weighted_mean(
        [
            (0.30, growth),
            (0.25, profitability),
            (0.15, leverage),
            (0.15, cash),
            (0.15, trend_adj),
        ]
    )
    if score is None:
        return None, "Unknown"
    return float(score), _quality_label(score)


def _quality_label(score: float) -> str:
    if score >= 75:
        return "Strong"
    if score >= 60:
        return "Healthy"
    if score >= 45:
        return "Adequate"
    if score >= 30:
        return "Weak"
    return "Stressed"


def _margin_to_score(margin: float | None, *, good: float) -> float | None:
    if margin is None:
        return None
    # good margin maps near 75; 0 maps near 40; negative near 15.
    return 40.0 + tanh_score(margin, good) * 0.4


def _margin_series(
    numerator: pd.Series | None,
    fallback_num: pd.Series | None,
    revenue: pd.Series | None,
) -> pd.Series | None:
    num = numerator if numerator is not None else fallback_num
    if num is None or revenue is None:
        return None
    aligned = pd.to_numeric(num, errors="coerce") / pd.to_numeric(revenue, errors="coerce").replace(0, pd.NA)
    aligned = aligned.dropna()
    return aligned if len(aligned) >= 2 else None


def _latest_margin(numerator: pd.Series | None, revenue: pd.Series | None) -> float | None:
    if numerator is None or revenue is None:
        return None
    num = pd.to_numeric(numerator, errors="coerce").dropna()
    den = pd.to_numeric(revenue, errors="coerce").dropna()
    if num.empty or den.empty:
        return None
    # Align on the newest shared column if possible.
    shared = [c for c in num.index if c in den.index]
    if not shared:
        return None
    d = float(den.loc[shared[0]])
    if d == 0:
        return None
    return float(num.loc[shared[0]]) / d


def _latest(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    cleaned = pd.to_numeric(series, errors="coerce").dropna()
    if cleaned.empty:
        return None
    return float(cleaned.iloc[0])


def _info_str(info: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _notes(snap: FundamentalsSnapshot, info: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if snap.pe_trailing is not None and snap.pe_trailing < 0:
        notes.append("Trailing P/E is negative (losses on a TTM basis).")
    if snap.debt_to_equity is not None and snap.debt_to_equity > 2.5:
        notes.append("High leverage (debt/equity above ~2.5x).")
    if snap.free_cash_flow is not None and snap.free_cash_flow < 0:
        notes.append("Latest annual free cash flow is negative.")
    if snap.revenue_growth_yoy is not None and snap.revenue_growth_yoy < -0.05:
        notes.append("Revenue contracted year over year.")
    currency = info.get("currency")
    if currency and currency != "USD":
        notes.append(f"Reported currency is {currency}; compare multiples with care.")
    return notes
