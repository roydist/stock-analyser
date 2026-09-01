from __future__ import annotations

import math

import numpy as np
import pytest

from stock_analyzer.config import TREND_WEIGHTS, parse_periods, score_label
from stock_analyzer.trend import add_indicators, find_swings, score_period, score_periods
from stock_analyzer.util import weighted_mean
from tests.fixtures import interpolate_swings, make_ohlcv, make_sine_ohlcv


def test_weights_sum_to_one() -> None:
    assert math.isclose(sum(TREND_WEIGHTS.values()), 1.0)


def test_uptrend_scores_positive() -> None:
    hist = make_ohlcv(800, drift=0.003, vol=0.0)
    trends = {t.period: t for t in score_periods(hist, ["1mo", "3mo", "6mo", "1y"])}
    for period, trend in trends.items():
        assert trend.score > 35, f"{period} expected strong uptrend, got {trend.score:.1f} ({trend.label})"
        assert "uptrend" in trend.label.lower()


def test_downtrend_scores_negative() -> None:
    hist = make_ohlcv(800, drift=-0.003, vol=0.0)
    trends = score_periods(hist, ["1mo", "3mo", "1y"])
    for trend in trends:
        assert trend.score < -35, f"{trend.period} expected downtrend, got {trend.score:.1f}"
        assert "downtrend" in trend.label.lower()


def test_sideways_near_neutral() -> None:
    hist = make_sine_ohlcv(400, amplitude=2.0)
    trend = score_period(hist, "3mo")
    assert abs(trend.score) < 35, f"sideways tape should not be strong, got {trend.score:.1f}"


def test_score_is_weighted_blend_of_components() -> None:
    hist = make_ohlcv(400, drift=0.002)
    trend = score_period(hist, "6mo")
    c = trend.components
    expected = weighted_mean(
        [
            (TREND_WEIGHTS["return"], c.return_score),
            (TREND_WEIGHTS["ma_alignment"], c.ma_alignment_score),
            (TREND_WEIGHTS["ma_slope"], c.ma_slope_score),
            (TREND_WEIGHTS["structure"], c.structure_score),
            (TREND_WEIGHTS["momentum"], c.momentum_score),
        ]
    )
    assert expected is not None
    assert abs(trend.score - expected) < 1e-6


def test_higher_highs_higher_lows() -> None:
    hist = interpolate_swings([100, 115, 108, 128, 118, 145, 132, 160], bars_each=14)
    trend = score_period(hist, "3mo")
    assert "higher high" in trend.components.structure_label
    assert trend.components.structure_score is not None
    assert trend.components.structure_score >= 50


def test_lower_highs_lower_lows() -> None:
    hist = interpolate_swings([160, 145, 152, 130, 140, 110, 122, 90], bars_each=14)
    trend = score_period(hist, "3mo")
    assert "lower high" in trend.components.structure_label
    assert trend.components.structure_score is not None
    assert trend.components.structure_score <= -50


def test_find_swings_detects_peaks_and_troughs() -> None:
    hist = interpolate_swings([10, 20, 12, 22, 14, 24], bars_each=10)
    peaks, troughs = find_swings(hist["Close"], order=4)
    assert len(peaks) >= 2
    assert len(troughs) >= 2
    assert peaks[-1] > peaks[0]
    assert troughs[-1] > troughs[0]


def test_rsi_hot_after_steady_rally() -> None:
    hist = make_ohlcv(60, start=50, drift=0.02, vol=0.0)
    indicated = add_indicators(hist)
    rsi = float(indicated["RSI"].iloc[-1])
    assert rsi > 70


def test_rsi_cold_after_steady_selloff() -> None:
    hist = make_ohlcv(60, start=50, drift=-0.02, vol=0.0)
    indicated = add_indicators(hist)
    rsi = float(indicated["RSI"].iloc[-1])
    assert rsi < 30


def test_macd_positive_in_uptrend() -> None:
    hist = make_ohlcv(120, drift=0.01, vol=0.0)
    trend = score_period(hist, "3mo")
    assert trend.components.macd_hist is not None
    assert trend.components.macd_hist > 0


def test_bullish_ma_stack() -> None:
    hist = make_ohlcv(300, drift=0.004, vol=0.0)
    trend = score_period(hist, "6mo")
    assert trend.components.ma_stack == "bullish"
    assert trend.components.price_vs_fast == "above"
    assert trend.components.ma_alignment_score == 100


def test_bearish_ma_stack() -> None:
    hist = make_ohlcv(300, drift=-0.004, vol=0.0)
    trend = score_period(hist, "6mo")
    assert trend.components.ma_stack == "bearish"
    assert trend.components.price_vs_fast == "below"
    assert trend.components.ma_alignment_score == -100


def test_labels_match_thresholds() -> None:
    assert score_label(80) == "Strong uptrend"
    assert score_label(25) == "Uptrend"
    assert score_label(0) == "Sideways / mixed"
    assert score_label(-25) == "Downtrend"
    assert score_label(-80) == "Strong downtrend"


def test_short_history_does_not_crash() -> None:
    hist = make_ohlcv(25, drift=0.002)
    trend = score_period(hist, "1mo")
    assert -100 <= trend.score <= 100
    assert trend.components.n_bars >= 5
    assert trend.components.last_close is not None


def test_too_short_history_raises() -> None:
    hist = make_ohlcv(3, drift=0.0)
    with pytest.raises(ValueError, match="Not enough bars"):
        score_period(hist, "1mo")


def test_parse_periods_validates() -> None:
    assert parse_periods("1mo, 1y") == ["1mo", "1y"]
    with pytest.raises(ValueError, match="Unknown"):
        parse_periods("1w")


def test_total_return_matches_window() -> None:
    hist = make_ohlcv(252, start=100, drift=0.0, vol=0.0)
    # zero drift still compounds 0, return ~0; use a known ratio instead
    hist = hist.copy()
    hist["Close"] = np.linspace(100, 150, len(hist))
    trend = score_period(hist, "1y")
    expected = 150 / 100 - 1
    # window is last 252 bars, which is the whole series
    assert abs(trend.components.total_return - expected) < 1e-9
