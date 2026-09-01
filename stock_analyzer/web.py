"""Tiny local web UI (stdlib only) for running the same analysis as the CLI."""

from __future__ import annotations

import html as html_lib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from stock_analyzer.analyze import analyze_tickers
from stock_analyzer.charts import png_to_data_uri, plot_period
from stock_analyzer.config import DEFAULT_PERIODS, DEFAULT_TICKERS, PERIODS, parse_periods, parse_tickers
from stock_analyzer.report import render_html


FORM = """
<form class="bar" method="get" action="/">
  <label>Tickers
    <input type="text" name="tickers" value="{tickers}" placeholder="AAPL TSLA HD"/>
  </label>
  <label>Periods
    <span class="checks">{checks}</span>
  </label>
  <button type="submit">Analyze</button>
</form>
<p class="meta">Local only ({host}:{port}). Uses Yahoo Finance via yfinance — no API key. Not investment advice.</p>
"""


def _checks(selected: list[str]) -> str:
    bits = []
    for key in PERIODS:
        checked = " checked" if key in selected else ""
        bits.append(
            f'<label><input type="checkbox" name="periods" value="{key}"{checked}/> {key}</label>'
        )
    return "".join(bits)


def serve(*, host: str = "127.0.0.1", port: int = 8000) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            sys_stderr_write = __import__("sys").stderr.write
            sys_stderr_write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path not in {"/", "/analyze"}:
                self.send_error(404)
                return
            qs = parse_qs(parsed.query)
            tickers_raw = (qs.get("tickers") or [" ".join(DEFAULT_TICKERS)])[0]
            selected_periods = qs.get("periods") or list(DEFAULT_PERIODS)
            try:
                tickers = parse_tickers(tickers_raw)
                periods = parse_periods(",".join(selected_periods))
            except ValueError as exc:
                page = render_html(
                    _empty_error(str(exc)),
                    form_html=FORM.format(
                        tickers=html_lib.escape(tickers_raw),
                        checks=_checks(list(DEFAULT_PERIODS)),
                        host=host,
                        port=port,
                    ),
                )
                self._send(page, 400)
                return

            form = FORM.format(
                tickers=html_lib.escape(" ".join(tickers)),
                checks=_checks(periods),
                host=host,
                port=port,
            )
            if "tickers" not in qs and "periods" not in qs:
                # First load: show the form and a short landing note, don't hit the network yet.
                landing = _landing_html(form)
                self._send(landing, 200)
                return

            try:
                report, histories = analyze_tickers(tickers, periods)
                uris: dict[str, str] = {}
                longest = max(periods, key=lambda p: PERIODS[p].bars)
                for ticker, history in histories.items():
                    try:
                        uris[ticker] = png_to_data_uri(plot_period(history, ticker, longest))
                    except Exception:
                        continue
                page = render_html(report, chart_data_uris=uris, form_html=form)
                self._send(page, 200)
            except Exception as exc:  # noqa: BLE001
                self._send(_error_page(str(exc), form), 500)

        def _send(self, page: str, status: int) -> None:
            data = page.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Stock analyzer UI on http://{host}:{port}  (Ctrl+C to stop)")
    print("Not investment advice. Data via Yahoo Finance / yfinance.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
        httpd.server_close()


def _landing_html(form: str) -> str:
    from stock_analyzer.models import AnalysisReport
    from stock_analyzer.report import utc_now_iso
    from stock_analyzer import DISCLAIMER
    from stock_analyzer.config import METHOD_SUMMARY

    report = AnalysisReport(
        tickers=[],
        periods=list(DEFAULT_PERIODS),
        generated_at=utc_now_iso(),
        method_summary=METHOD_SUMMARY,
        disclaimer=DISCLAIMER,
    )
    extra = form + "<p>Enter tickers and click Analyze. Default demo list is the sample holdings set.</p>"
    return render_html(report, form_html=extra)


def _empty_error(message: str):
    from stock_analyzer.models import AnalysisReport, TickerAnalysis
    from stock_analyzer.report import utc_now_iso
    from stock_analyzer import DISCLAIMER
    from stock_analyzer.config import METHOD_SUMMARY

    return AnalysisReport(
        tickers=[TickerAnalysis(ticker="?", error=message, headline=message, synthesis=message)],
        periods=list(DEFAULT_PERIODS),
        generated_at=utc_now_iso(),
        method_summary=METHOD_SUMMARY,
        disclaimer=DISCLAIMER,
    )


def _error_page(message: str, form: str) -> str:
    return render_html(_empty_error(message), form_html=form)
