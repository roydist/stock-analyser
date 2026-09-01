#!/usr/bin/env python3
"""Write examples/sample_report.{md,html} from offline fixtures (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_analyzer.analyze import analyze_tickers
from stock_analyzer.charts import export_charts, png_to_data_uri
from stock_analyzer.data import FixtureProvider
from stock_analyzer.report import render_html, render_markdown
from tests.fixtures import make_ohlcv, make_sine_ohlcv, strong_company_bundle, weak_company_bundle


def main() -> int:
    dest = ROOT / "examples"
    dest.mkdir(parents=True, exist_ok=True)
    charts_dir = dest / "charts"

    provider = FixtureProvider(
        histories={
            "ACME": make_ohlcv(1100, start=80, drift=0.0022, vol=0.0, seed=1),
            "FADE": make_ohlcv(1100, start=140, drift=-0.0012, vol=0.0, seed=2),
            "CHOP": make_sine_ohlcv(1100, center=90, amplitude=8),
        },
        fundamentals={
            "ACME": strong_company_bundle(),
            "FADE": weak_company_bundle(),
        },
    )
    periods = ["1mo", "3mo", "6mo", "1y", "5y"]
    report, histories = analyze_tickers(["ACME", "FADE", "CHOP"], periods, provider=provider)
    paths = export_charts(histories, periods, charts_dir)
    uris = {key: png_to_data_uri(Path(path).read_bytes()) for key, path in paths.items()}

    md_path = dest / "sample_report.md"
    html_path = dest / "sample_report.html"
    # Markdown image paths relative to examples/
    rel = {key: str(Path(path).relative_to(dest)) for key, path in paths.items()}
    overview_rel = {k: v for k, v in rel.items() if ":" not in k}
    overview_uris = {k: v for k, v in uris.items() if ":" not in k}

    note = (
        "> **Note:** This checked-in sample is generated from *synthetic* OHLCV and "
        "fundamentals (`python examples/generate_sample.py`), not live market data. "
        "Run `python -m stock_analyzer AAPL TSLA --periods 1mo,3mo,6mo,1y,5y` for a live Yahoo report.\n\n"
    )
    md_path.write_text(note + render_markdown(report, chart_paths=overview_rel), encoding="utf-8")
    html_path.write_text(render_html(report, chart_data_uris=overview_uris), encoding="utf-8")
    print(f"Wrote {md_path}")
    print(f"Wrote {html_path}")
    print(f"Wrote charts under {charts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
