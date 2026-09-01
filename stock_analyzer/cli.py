"""Command-line entry: ``python -m stock_analyzer AAPL TSLA --periods 1mo,3mo,6mo,1y,5y``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from stock_analyzer import DISCLAIMER, __version__
from stock_analyzer.analyze import analyze_tickers
from stock_analyzer.charts import export_charts, png_to_data_uri, plot_period
from stock_analyzer.config import DEFAULT_PERIODS, DEFAULT_TICKERS, PERIODS, parse_periods, parse_tickers
from stock_analyzer.report import render_html, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-analyzer",
        description=(
            "Analyze US equity price trends across multiple time periods and "
            "combine them with company fundamentals into a readable report. "
            "Not investment advice."
        ),
        epilog=DISCLAIMER,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help=f"US equity tickers (default: {' '.join(DEFAULT_TICKERS)})",
    )
    parser.add_argument(
        "--periods",
        default=",".join(DEFAULT_PERIODS),
        help=f"Comma-separated periods. Supported: {', '.join(PERIODS)}. Default: {','.join(DEFAULT_PERIODS)}",
    )
    parser.add_argument("-o", "--output", help="Write Markdown report to this path (also printed to stdout).")
    parser.add_argument("--html", help="Write a self-contained HTML report to this path.")
    parser.add_argument("--json", dest="json_path", help="Write machine-readable JSON to this path.")
    parser.add_argument(
        "--charts-dir",
        help="Export PNG charts (price + SMAs) for each ticker and period into this directory.",
    )
    parser.add_argument(
        "--web",
        action="store_true",
        help="Start a local web UI (binds to --host/--port, default 127.0.0.1:8000).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Web UI bind host.")
    parser.add_argument("--port", type=int, default=8000, help="Web UI bind port.")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.web:
        from stock_analyzer.web import serve

        serve(host=args.host, port=args.port)
        return 0

    try:
        periods = parse_periods(args.periods)
        tickers = [t.strip().upper() for t in args.tickers if t.strip()] or list(DEFAULT_TICKERS)
        # Allow a single comma-separated token as well as separate args.
        if len(tickers) == 1 and ("," in tickers[0] or " " in tickers[0]):
            tickers = parse_tickers(tickers[0])
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"# Analyzing {', '.join(tickers)} over {', '.join(periods)} …", file=sys.stderr)
    print(f"# {DISCLAIMER}", file=sys.stderr)
    report, histories = analyze_tickers(tickers, periods)

    chart_paths: dict[str, str] = {}
    chart_uris: dict[str, str] = {}
    if args.charts_dir:
        dest = Path(args.charts_dir)
        chart_paths = export_charts(histories, periods, dest)
        for key, path in chart_paths.items():
            if ":" in key:
                chart_uris[key] = png_to_data_uri(Path(path).read_bytes())
        # Also keep overview keys
        for ticker in histories:
            if ticker in chart_paths:
                chart_uris.setdefault(ticker, png_to_data_uri(Path(chart_paths[ticker]).read_bytes()))
    elif args.html:
        # Embed one overview chart per ticker (longest period) so HTML stays portable.
        longest = max(periods, key=lambda p: PERIODS[p].bars)
        for ticker, history in histories.items():
            try:
                png = plot_period(history, ticker, longest)
                chart_uris[ticker] = png_to_data_uri(png)
            except Exception as exc:  # noqa: BLE001
                logging.warning("Chart failed for %s: %s", ticker, exc)

    markdown = render_markdown(report, chart_paths=chart_paths)
    print(markdown)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(f"# Wrote {out}", file=sys.stderr)
    if args.html:
        html_path = Path(args.html)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(render_html(report, chart_data_uris=chart_uris), encoding="utf-8")
        print(f"# Wrote {html_path}", file=sys.stderr)
    if args.json_path:
        json_path = Path(args.json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report.to_dict(), indent=2, default=str), encoding="utf-8")
        print(f"# Wrote {json_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
