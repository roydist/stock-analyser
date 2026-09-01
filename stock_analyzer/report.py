"""Markdown, HTML, and ASCII-table report rendering."""

from __future__ import annotations

import html
from datetime import datetime, timezone

from stock_analyzer import DISCLAIMER
from stock_analyzer.models import AnalysisReport, FundamentalsSnapshot, PeriodTrend, TickerAnalysis
from stock_analyzer.util import fmt_compact, fmt_number, fmt_pct, fmt_score


def render_markdown(report: AnalysisReport, *, chart_paths: dict[str, str] | None = None) -> str:
    chart_paths = chart_paths or {}
    lines: list[str] = [
        "# Stock trend + fundamentals report",
        "",
        f"Generated: {report.generated_at}  ",
        f"Data source: {report.source}",
        "",
        f"> **Disclaimer:** {report.disclaimer}",
        "",
        "## Cross-ticker scoreboard",
        "",
        _scoreboard_md(report),
        "",
        "## Method",
        "",
        "```",
        report.method_summary,
        "```",
        "",
    ]
    for item in report.tickers:
        lines.extend(_ticker_md(item, chart_paths))
        lines.append("")
    lines.extend(
        [
            "---",
            "",
            f"_{DISCLAIMER}_",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def render_html(
    report: AnalysisReport,
    *,
    chart_data_uris: dict[str, str] | None = None,
    form_html: str = "",
) -> str:
    chart_data_uris = chart_data_uris or {}
    body = [
        "<article class='wrap'>",
        "<h1>Stock trend + fundamentals report</h1>",
        f"<p class='meta'>Generated {html.escape(report.generated_at)} · {html.escape(report.source)}</p>",
        f"<p class='disclaimer'><strong>Disclaimer:</strong> {html.escape(report.disclaimer)}</p>",
        form_html,
        "<h2>Cross-ticker scoreboard</h2>",
        _scoreboard_html(report),
        "<details><summary>Scoring method</summary><pre>",
        html.escape(report.method_summary),
        "</pre></details>",
    ]
    for item in report.tickers:
        body.append(_ticker_html(item, chart_data_uris))
    body.append("</article>")
    return _HTML_PAGE.format(body="\n".join(body))


def _scoreboard_md(report: AnalysisReport) -> str:
    headers = ["Ticker", *[p for p in report.periods], "Quality", "Headline"]
    rows: list[list[str]] = []
    for item in report.tickers:
        by_p = item.trend_by_period()
        row = [item.ticker]
        if item.error:
            row.extend(["err"] * len(report.periods))
            q = "—"
        else:
            for period in report.periods:
                t = by_p.get(period)
                row.append(fmt_score(t.score) if t else "—")
            q = (
                f"{item.fundamentals.quality_label} ({item.fundamentals.quality_score:.0f})"
                if item.fundamentals and item.fundamentals.quality_score is not None
                else "—"
            )
        row.append(q)
        row.append(item.headline or item.error or "")
        rows.append(row)
    return _pipe_table(headers, rows)


def _scoreboard_html(report: AnalysisReport) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in ["Ticker", *report.periods, "Quality", "Headline"])
    rows = []
    for item in report.tickers:
        by_p = item.trend_by_period()
        cells = [f"<td><strong>{html.escape(item.ticker)}</strong></td>"]
        if item.error:
            for _ in report.periods:
                cells.append("<td class='err'>err</td>")
        else:
            for period in report.periods:
                t = by_p.get(period)
                cells.append(_score_td(t.score if t else None))
        if item.fundamentals and item.fundamentals.quality_score is not None:
            cells.append(
                f"<td>{html.escape(item.fundamentals.quality_label)} "
                f"({item.fundamentals.quality_score:.0f})</td>"
            )
        else:
            cells.append("<td>—</td>")
        cells.append(f"<td class='headline'>{html.escape(item.headline or item.error or '')}</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f"<table class='board'><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _ticker_md(item: TickerAnalysis, chart_paths: dict[str, str]) -> list[str]:
    lines = [f"## {item.ticker}", ""]
    if item.error:
        lines += [f"**Error:** {item.error}", ""]
        return lines
    lines += [f"**{item.headline}**", "", item.synthesis, ""]
    if item.horizons:
        h = item.horizons
        lines += [
            "### Multi-period view",
            "",
            f"- Short-term: {h.short_label or 'n/a'} ({fmt_score(h.short)})",
            f"- Medium-term: {h.medium_label or 'n/a'} ({fmt_score(h.medium)})",
            f"- Long-term: {h.long_label or 'n/a'} ({fmt_score(h.long)})",
            f"- Agreement: **{h.agreement}** — {h.agreement_note}",
            "",
        ]
    lines += ["### Trend components", "", _trend_table_md(item.trends), ""]
    if item.fundamentals:
        lines += ["### Fundamentals", "", _fundamentals_md(item.fundamentals), ""]
    # Charts: prefer per-period keys ticker:period, else ticker overview.
    shown = False
    for trend in item.trends:
        key = f"{item.ticker}:{trend.period}"
        if key in chart_paths:
            lines += [f"![{item.ticker} {trend.period}]({chart_paths[key]})", ""]
            shown = True
    if not shown:
        overview = chart_paths.get(item.ticker)
        if overview:
            lines += [f"![{item.ticker}]({overview})", ""]
    return lines


def _trend_table_md(trends: list[PeriodTrend]) -> str:
    headers = [
        "Period",
        "Horizon",
        "Score",
        "Label",
        "Return",
        "SMA stack",
        "SMA slope",
        "Structure",
        "RSI",
        "MACD hist",
    ]
    rows = []
    for t in trends:
        c = t.components
        slope = fmt_pct(c.sma_fast_slope_pct) if c.sma_fast_slope_pct is not None else "—"
        rows.append(
            [
                t.period,
                t.horizon,
                fmt_score(t.score),
                t.label,
                fmt_pct(c.total_return),
                c.ma_stack or "—",
                slope,
                c.structure_label,
                fmt_number(c.rsi, digits=1),
                fmt_number(c.macd_hist, digits=2),
            ]
        )
    return _pipe_table(headers, rows)


def _fundamentals_md(f: FundamentalsSnapshot) -> str:
    rows = [
        ["Name", f.name or "—"],
        ["Sector / industry", " / ".join(x for x in (f.sector, f.industry) if x) or "—"],
        ["Quality", f"{f.quality_label} ({f.quality_score:.0f}/100)" if f.quality_score is not None else "—"],
        ["Revenue YoY", fmt_pct(f.revenue_growth_yoy)],
        ["Revenue CAGR", fmt_pct(f.revenue_cagr)],
        ["Earnings YoY", fmt_pct(f.earnings_growth_yoy)],
        ["EPS / NI trend", f.eps_trend],
        ["Margin trend", f.margin_trend],
        ["Gross / op / profit margin", f"{fmt_pct(f.gross_margin, signed=False)} / {fmt_pct(f.operating_margin, signed=False)} / {fmt_pct(f.profit_margin, signed=False)}"],
        ["ROE / ROA", f"{fmt_pct(f.roe, signed=False)} / {fmt_pct(f.roa, signed=False)}"],
        ["Trailing / forward P/E", f"{fmt_number(f.pe_trailing, digits=1)} / {fmt_number(f.pe_forward, digits=1)}"],
        ["P/S / P/B / EV/EBITDA", f"{fmt_number(f.ps, digits=1)} / {fmt_number(f.pb, digits=1)} / {fmt_number(f.ev_ebitda, digits=1)}"],
        ["Debt / equity", f"{f.debt_to_equity:.2f}x" if f.debt_to_equity is not None else "—"],
        ["Free cash flow", f"{fmt_compact(f.free_cash_flow)} ({f.fcf_trend})"],
    ]
    if f.notes:
        rows.append(["Notes", " ".join(f.notes)])
    return _pipe_table(["Field", "Value"], rows)


def _ticker_html(item: TickerAnalysis, chart_data_uris: dict[str, str]) -> str:
    if item.error:
        return f"<section><h2>{html.escape(item.ticker)}</h2><p class='err'>{html.escape(item.error)}</p></section>"
    parts = [
        f"<section id='{html.escape(item.ticker)}'>",
        f"<h2>{html.escape(item.ticker)}</h2>",
        f"<p class='lead'>{html.escape(item.headline)}</p>",
        _mdish_paragraphs(item.synthesis),
    ]
    if item.horizons:
        h = item.horizons
        parts.append("<h3>Multi-period view</h3><ul>")
        parts.append(f"<li>Short-term: {html.escape(h.short_label or 'n/a')} ({html.escape(fmt_score(h.short))})</li>")
        parts.append(f"<li>Medium-term: {html.escape(h.medium_label or 'n/a')} ({html.escape(fmt_score(h.medium))})</li>")
        parts.append(f"<li>Long-term: {html.escape(h.long_label or 'n/a')} ({html.escape(fmt_score(h.long))})</li>")
        parts.append(
            f"<li>Agreement: <strong>{html.escape(h.agreement)}</strong> — {html.escape(h.agreement_note)}</li>"
        )
        parts.append("</ul>")
    parts.append("<h3>Trend components</h3>")
    parts.append(_trend_table_html(item.trends))
    if item.fundamentals:
        parts.append("<h3>Fundamentals</h3>")
        parts.append(_fundamentals_html(item.fundamentals))
    for trend in item.trends:
        key = f"{item.ticker}:{trend.period}"
        if key in chart_data_uris:
            parts.append(
                f"<figure><img alt='{html.escape(item.ticker)} {html.escape(trend.period)}' "
                f"src='{chart_data_uris[key]}'/><figcaption>{html.escape(item.ticker)} {html.escape(trend.period)}</figcaption></figure>"
            )
    if not any(f"{item.ticker}:{t.period}" in chart_data_uris for t in item.trends):
        if item.ticker in chart_data_uris:
            parts.append(
                f"<figure><img alt='{html.escape(item.ticker)}' src='{chart_data_uris[item.ticker]}'/></figure>"
            )
    parts.append("</section>")
    return "\n".join(parts)


def _trend_table_html(trends: list[PeriodTrend]) -> str:
    headers = ["Period", "Horizon", "Score", "Label", "Return", "SMA stack", "SMA slope", "Structure", "RSI", "MACD hist"]
    head = "".join(f"<th>{h}</th>" for h in headers)
    rows = []
    for t in trends:
        c = t.components
        slope = fmt_pct(c.sma_fast_slope_pct) if c.sma_fast_slope_pct is not None else "—"
        cells = [
            t.period,
            t.horizon,
            None,  # score handled separately
            t.label,
            fmt_pct(c.total_return),
            c.ma_stack or "—",
            slope,
            c.structure_label,
            fmt_number(c.rsi, digits=1),
            fmt_number(c.macd_hist, digits=2),
        ]
        tds = [f"<td>{html.escape(str(cells[0]))}</td>", f"<td>{html.escape(str(cells[1]))}</td>", _score_td(t.score)]
        tds.extend(f"<td>{html.escape(str(x))}</td>" for x in cells[3:])
        rows.append("<tr>" + "".join(tds) + "</tr>")
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def _fundamentals_html(f: FundamentalsSnapshot) -> str:
    md = _fundamentals_md(f)
    # Reuse markdown table -> simple HTML conversion of our pipe tables.
    lines = [ln for ln in md.splitlines() if ln.startswith("|")]
    rows = []
    for i, ln in enumerate(lines):
        cols = [c.strip() for c in ln.strip("|").split("|")]
        if i == 1 and set("".join(cols)) <= set("-: "):
            continue
        tag = "th" if i == 0 else "td"
        rows.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cols) + "</tr>")
    return f"<table>{''.join(rows)}</table>"


def _mdish_paragraphs(text: str) -> str:
    blocks = []
    for para in text.split("\n\n"):
        escaped = html.escape(para)
        escaped = escaped.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
        # Handle remaining ** pairs.
        while "**" in escaped:
            escaped = escaped.replace("**", "<strong>", 1).replace("**", "</strong>", 1)
        blocks.append(f"<p>{escaped}</p>")
    return "\n".join(blocks)


def _score_td(score: float | None) -> str:
    if score is None:
        return "<td>—</td>"
    cls = "flat"
    if score >= 50:
        cls = "up-strong"
    elif score >= 20:
        cls = "up"
    elif score <= -50:
        cls = "down-strong"
    elif score <= -20:
        cls = "down"
    return f"<td class='{cls}'>{html.escape(fmt_score(score))}</td>"


def _pipe_table(headers: list[str], rows: list[list[str]]) -> str:
    widths = [len(h) for h in headers]
    norm_rows = []
    for row in rows:
        padded = [str(c).replace("\n", " ") for c in row] + [""] * (len(headers) - len(row))
        padded = padded[: len(headers)]
        norm_rows.append(padded)
        for i, cell in enumerate(padded):
            widths[i] = max(widths[i], len(cell))
    def fmt_row(vals: list[str]) -> str:
        return "| " + " | ".join(v.ljust(widths[i]) for i, v in enumerate(vals)) + " |"
    sep = "| " + " | ".join("-" * w for w in widths) + " |"
    return "\n".join([fmt_row(headers), sep, *[fmt_row(r) for r in norm_rows]])


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Stock analyzer report</title>
  <style>
    :root {{ color-scheme: light dark; }}
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; background: #0f1419; color: #e7ecf1; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px 20px 64px; }}
    h1, h2, h3 {{ line-height: 1.25; }}
    h1 {{ font-size: 1.8rem; }}
    a {{ color: #8cb4ff; }}
    .meta {{ color: #9aa7b5; }}
    .disclaimer {{ background: #1b2430; border-left: 4px solid #d4a017; padding: 12px 14px; }}
    .lead {{ font-size: 1.05rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 12px 0 20px; font-size: 0.92rem; }}
    th, td {{ border-bottom: 1px solid #2a3542; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ color: #9aa7b5; font-weight: 600; }}
    .board td.headline {{ font-size: 0.86rem; color: #c5d0da; }}
    .up-strong {{ color: #3dd68c; font-weight: 700; }}
    .up {{ color: #7ee0ad; }}
    .down {{ color: #f0a0a0; }}
    .down-strong {{ color: #ff6b6b; font-weight: 700; }}
    .flat {{ color: #c5d0da; }}
    .err {{ color: #ff6b6b; }}
    details {{ background: #1b2430; padding: 10px 14px; margin: 16px 0 28px; }}
    pre {{ white-space: pre-wrap; font-size: 0.85rem; }}
    figure {{ margin: 16px 0; }}
    img {{ max-width: 100%; background: #fff; border-radius: 6px; }}
    form.bar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 18px 0 8px; }}
    form.bar label {{ display: flex; flex-direction: column; font-size: 0.85rem; color: #9aa7b5; gap: 4px; }}
    form.bar input[type=text] {{ min-width: 280px; padding: 8px; border-radius: 6px; border: 1px solid #2a3542; background: #0f1419; color: inherit; }}
    form.bar button {{ padding: 9px 14px; border: 0; border-radius: 6px; background: #3d7eff; color: white; font-weight: 600; cursor: pointer; }}
    .checks {{ display: flex; gap: 10px; flex-wrap: wrap; }}
    section {{ margin-top: 36px; padding-top: 8px; border-top: 1px solid #2a3542; }}
  </style>
</head>
<body>
{body}
</body>
</html>
"""
