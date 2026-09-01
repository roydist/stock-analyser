from __future__ import annotations

from stock_analyzer.models import FundamentalsSnapshot, TickerAnalysis
from stock_analyzer.synthesis import build_horizons, synthesize
from tests.fixtures import stub_trend


def _analysis(trends, fund=None, ticker="TEST") -> TickerAnalysis:
    item = TickerAnalysis(ticker=ticker, trends=list(trends), fundamentals=fund)
    return synthesize(item)


def test_conflicting_short_pullback_in_long_uptrend() -> None:
    item = _analysis([stub_trend("1mo", -40), stub_trend("3mo", -25), stub_trend("1y", 35), stub_trend("5y", 70)])
    assert item.horizons is not None
    assert item.horizons.agreement == "conflicting"
    assert "pullback" in item.horizons.agreement_note.lower()
    assert "pullback" in item.headline.lower() or "uptrend" in item.headline.lower()


def test_aligned_uptrend() -> None:
    item = _analysis([stub_trend("1mo", 40), stub_trend("6mo", 50), stub_trend("5y", 60)])
    assert item.horizons is not None
    assert item.horizons.agreement == "aligned"
    assert "uptrend" in item.headline.lower()


def test_price_up_earnings_down_divergence() -> None:
    fund = FundamentalsSnapshot(
        ticker="TEST",
        name="Test Co",
        eps_trend="deteriorating",
        margin_trend="deteriorating",
        quality_score=42,
        quality_label="Weak",
        revenue_growth_yoy=-0.08,
    )
    item = _analysis([stub_trend("1y", 55), stub_trend("5y", 48)], fund=fund)
    text = (item.headline + " " + item.synthesis).lower()
    assert "deteriorat" in text
    assert "rising" in text or "uptrend" in text
    assert "divergence" in item.synthesis.lower() or "cautionary" in item.synthesis.lower()


def test_price_down_earnings_up_disconnect() -> None:
    fund = FundamentalsSnapshot(
        ticker="TEST",
        name="Test Co",
        eps_trend="improving",
        margin_trend="improving",
        quality_score=70,
        quality_label="Healthy",
        revenue_growth_yoy=0.12,
    )
    item = _analysis([stub_trend("1y", -45), stub_trend("5y", -30)], fund=fund)
    text = (item.headline + " " + item.synthesis).lower()
    assert "improving" in text
    assert "falling" in text or "downtrend" in text
    assert "disconnect" in item.synthesis.lower() or "falling while" in item.synthesis.lower()


def test_uptrend_with_improving_margins_phrase() -> None:
    fund = FundamentalsSnapshot(
        ticker="TEST",
        name="Test Co",
        eps_trend="improving",
        margin_trend="improving",
        quality_score=80,
        quality_label="Strong",
        revenue_growth_yoy=0.15,
        operating_margin=0.22,
    )
    item = _analysis([stub_trend("3mo", 30), stub_trend("1y", 40), stub_trend("5y", 55)], fund=fund)
    text = (item.headline + " " + item.synthesis).lower()
    assert "improving" in text
    assert "supportive fundamentals" in item.synthesis.lower()


def test_horizon_averages() -> None:
    view = build_horizons([stub_trend("1mo", 10), stub_trend("3mo", 30), stub_trend("5y", -40)])
    assert view.short is not None
    assert abs(view.short - 20) < 1e-9
    assert view.long == -40
    assert view.medium is None
    assert view.agreement == "conflicting"
