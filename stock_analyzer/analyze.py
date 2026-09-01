"""Orchestrate fetch → trend → fundamentals → synthesis for one or more tickers."""

from __future__ import annotations

import logging

from stock_analyzer import DISCLAIMER
from stock_analyzer.config import METHOD_SUMMARY
from stock_analyzer.data import MarketDataProvider, YahooFetcher
from stock_analyzer.fundamentals import analyze_fundamentals
from stock_analyzer.models import AnalysisReport, TickerAnalysis
from stock_analyzer.report import utc_now_iso
from stock_analyzer.synthesis import build_horizons, synthesize
from stock_analyzer.trend import score_periods


def analyze_tickers(
    tickers: list[str],
    periods: list[str],
    provider: MarketDataProvider | None = None,
) -> tuple[AnalysisReport, dict]:
    provider = provider or YahooFetcher()
    analyses: list[TickerAnalysis] = []
    histories: dict = {}
    for ticker in tickers:
        analyses.append(analyze_ticker(ticker, periods, provider, histories))
    report = AnalysisReport(
        tickers=analyses,
        periods=list(periods),
        generated_at=utc_now_iso(),
        method_summary=METHOD_SUMMARY,
        disclaimer=DISCLAIMER,
    )
    return report, histories


def analyze_ticker(
    ticker: str,
    periods: list[str],
    provider: MarketDataProvider,
    histories: dict | None = None,
) -> TickerAnalysis:
    symbol = ticker.strip().upper()
    analysis = TickerAnalysis(ticker=symbol)
    try:
        history = provider.history(symbol, periods)
        if histories is not None:
            histories[symbol] = history
        analysis.trends = score_periods(history, periods)
        analysis.horizons = build_horizons(analysis.trends)
    except Exception as exc:  # noqa: BLE001 — keep one ticker from sinking the run
        analysis.error = f"Could not score price trend: {exc}"
        return synthesize(analysis)

    try:
        bundle = provider.fundamentals_bundle(symbol)
        analysis.fundamentals = analyze_fundamentals(symbol, bundle)
    except Exception as exc:  # noqa: BLE001
        logging.warning("Fundamentals unavailable for %s: %s", symbol, exc)
        analysis.fundamentals = None

    return synthesize(analysis)
