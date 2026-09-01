from __future__ import annotations

from stock_analyzer.fundamentals import analyze_fundamentals, quality_score
from stock_analyzer.models import FundamentalsSnapshot
from tests.fixtures import strong_company_bundle, weak_company_bundle


def test_revenue_yoy_and_cagr() -> None:
    snap = analyze_fundamentals("ACME", strong_company_bundle())
    # 120/100 - 1 = 0.20; CAGR over 2 steps: (120/80)^(1/2) - 1 = 0.2247
    assert snap.revenue_growth_yoy is not None
    assert abs(snap.revenue_growth_yoy - 0.20) < 1e-9
    assert snap.revenue_cagr is not None
    assert abs(snap.revenue_cagr - ((120 / 80) ** 0.5 - 1)) < 1e-9


def test_eps_and_margin_trends_improving() -> None:
    snap = analyze_fundamentals("ACME", strong_company_bundle())
    assert snap.eps_trend == "improving"
    assert snap.margin_trend in {"improving", "stable"}
    assert snap.fcf_trend == "improving"
    assert snap.free_cash_flow == 20.0


def test_debt_equity_yahoo_percent_normalized() -> None:
    snap = analyze_fundamentals("ACME", strong_company_bundle())
    assert snap.debt_to_equity is not None
    assert abs(snap.debt_to_equity - 0.40) < 1e-9


def test_strong_company_quality_beats_weak() -> None:
    strong = analyze_fundamentals("ACME", strong_company_bundle())
    weak = analyze_fundamentals("FADE", weak_company_bundle())
    assert strong.quality_score is not None
    assert weak.quality_score is not None
    assert strong.quality_score - weak.quality_score > 25
    assert strong.quality_label in {"Strong", "Healthy"}
    assert weak.quality_label in {"Weak", "Stressed"}
    assert weak.eps_trend == "deteriorating"
    assert weak.revenue_growth_yoy is not None and weak.revenue_growth_yoy < 0


def test_missing_statements_still_use_info() -> None:
    from stock_analyzer.data import FundamentalsBundle

    bundle = FundamentalsBundle(
        info={
            "longName": "Info Only Inc",
            "trailingPE": 12.0,
            "revenueGrowth": 0.08,
            "profitMargins": 0.11,
            "operatingMargins": 0.15,
            "returnOnEquity": 0.18,
            "debtToEquity": 0.5,
            "freeCashflow": 1e9,
        }
    )
    snap = analyze_fundamentals("INFO", bundle)
    assert snap.name == "Info Only Inc"
    assert snap.pe_trailing == 12.0
    assert snap.revenue_growth_yoy is not None
    assert abs(snap.revenue_growth_yoy - 0.08) < 1e-9
    assert snap.quality_score is not None


def test_quality_score_handles_empty_snapshot() -> None:
    score, label = quality_score(FundamentalsSnapshot(ticker="X"))
    assert score is None
    assert label == "Unknown"
