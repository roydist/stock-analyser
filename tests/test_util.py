from __future__ import annotations

from stock_analyzer.config import parse_tickers
from stock_analyzer.util import as_unit_ratio, cagr, debt_equity_ratio, tanh_score, yoy_growth
import pandas as pd


def test_tanh_score_symmetric_and_capped() -> None:
    assert abs(tanh_score(0.0, 0.2)) < 1e-9
    assert tanh_score(0.2, 0.2) > 50
    assert tanh_score(-0.2, 0.2) < -50
    assert tanh_score(10.0, 0.2) <= 100
    assert tanh_score(-10.0, 0.2) >= -100


def test_yoy_and_cagr() -> None:
    s = pd.Series([120.0, 100.0, 80.0])
    assert abs(yoy_growth(s) - 0.20) < 1e-9
    assert abs(cagr(s) - ((120 / 80) ** 0.5 - 1)) < 1e-9


def test_unit_ratio_and_debt() -> None:
    assert as_unit_ratio(0.15) == 0.15
    assert abs(as_unit_ratio(15.0) - 0.15) < 1e-9
    assert abs(debt_equity_ratio(140.0) - 1.40) < 1e-9
    assert abs(debt_equity_ratio(0.8) - 0.8) < 1e-9


def test_parse_tickers() -> None:
    assert parse_tickers("aapl, tsla hd") == ["AAPL", "TSLA", "HD"]
    assert parse_tickers(None)[0] == "AAPL"
