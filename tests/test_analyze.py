from __future__ import annotations

from pathlib import Path

from stock_analyzer.analyze import analyze_tickers
from stock_analyzer.charts import plot_period
from stock_analyzer.cli import build_parser
from stock_analyzer.data import FixtureProvider
from stock_analyzer.report import render_html, render_markdown
from tests.fixtures import make_ohlcv, strong_company_bundle, weak_company_bundle


def _provider() -> FixtureProvider:
    return FixtureProvider(
        histories={
            "ACME": make_ohlcv(900, drift=0.0025, vol=0.0),
            "FADE": make_ohlcv(900, drift=-0.0015, vol=0.0),
        },
        fundamentals={"ACME": strong_company_bundle(), "FADE": weak_company_bundle()},
    )


def test_end_to_end_offline_report() -> None:
    report, histories = analyze_tickers(["ACME", "FADE", "MISSING"], ["1mo", "3mo", "6mo", "1y"], provider=_provider())
    assert "MISSING" in [t.ticker for t in report.tickers]
    missing = next(t for t in report.tickers if t.ticker == "MISSING")
    assert missing.error

    acme = next(t for t in report.tickers if t.ticker == "ACME")
    fade = next(t for t in report.tickers if t.ticker == "FADE")
    assert acme.trends
    assert fade.trends
    assert acme.trends[-1].score > fade.trends[-1].score
    assert acme.fundamentals is not None
    assert "Acme" in (acme.fundamentals.name or "")

    md = render_markdown(report)
    assert "ACME" in md
    assert "FADE" in md
    assert "Disclaimer" in md or "disclaimer" in md.lower()
    assert "not investment advice" in md.lower()
    assert "Return (30%)" in md or "return (30%)" in md.lower()
    assert "Cross-ticker scoreboard" in md
    assert "Multi-period view" in md

    html = render_html(report)
    assert "<table" in html
    assert "ACME" in html
    assert "disclaimer" in html.lower()


def test_chart_png(tmp_path: Path) -> None:
    hist = make_ohlcv(300, drift=0.002)
    dest = tmp_path / "acme_1y.png"
    data = plot_period(hist, "ACME", "1y", dest=dest)
    assert dest.exists()
    assert dest.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_cli_parser_defaults() -> None:
    ns = build_parser().parse_args(["AAPL", "TSLA", "--periods", "1mo,1y"])
    assert ns.tickers == ["AAPL", "TSLA"]
    assert ns.periods == "1mo,1y"
    ns2 = build_parser().parse_args(["--web", "--port", "9001"])
    assert ns2.web is True
    assert ns2.port == 9001


def test_analyze_isolates_ticker_errors() -> None:
    report, _ = analyze_tickers(["ACME", "NOPE"], ["1mo"], provider=_provider())
    by = {t.ticker: t for t in report.tickers}
    assert by["ACME"].error is None
    assert by["NOPE"].error
