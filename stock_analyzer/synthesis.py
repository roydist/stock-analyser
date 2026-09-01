"""Combine multi-period trend scores with fundamentals into a short narrative."""

from __future__ import annotations

from stock_analyzer.config import HORIZON_PERIODS, score_label
from stock_analyzer.models import FundamentalsSnapshot, HorizonView, PeriodTrend, TickerAnalysis
from stock_analyzer.util import fmt_pct, fmt_score, weighted_mean


def build_horizons(trends: list[PeriodTrend]) -> HorizonView:
    by_horizon: dict[str, list[float]] = {"short": [], "medium": [], "long": []}
    for trend in trends:
        if trend.horizon in by_horizon:
            by_horizon[trend.horizon].append(trend.score)

    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return sum(values) / len(values)

    short, medium, long = _avg(by_horizon["short"]), _avg(by_horizon["medium"]), _avg(by_horizon["long"])
    present = [(name, val) for name, val in (("short", short), ("medium", medium), ("long", long)) if val is not None]
    agreement, note = _agreement(present)
    return HorizonView(
        short=short,
        medium=medium,
        long=long,
        short_label=score_label(short) if short is not None else None,
        medium_label=score_label(medium) if medium is not None else None,
        long_label=score_label(long) if long is not None else None,
        agreement=agreement,
        agreement_note=note,
    )


def _agreement(present: list[tuple[str, float]]) -> tuple[str, str]:
    if len(present) <= 1:
        horizon = present[0][0] if present else "requested"
        return "single-horizon", f"Only the {horizon}-term window was scored."

    signed = [(name, _bucket(score)) for name, score in present]
    buckets = {b for _, b in signed}
    names = ", ".join(f"{n}-term {score_label(s).lower()} ({s:+.0f})" for n, s in present)

    if buckets == {"up"} or buckets == {"down"}:
        direction = "uptrend" if "up" in buckets else "downtrend"
        article = "an" if direction == "uptrend" else "a"
        return "aligned", f"Timeframes agree on {article} {direction}: {names}."
    if "up" in buckets and "down" in buckets:
        short = next((s for n, s in present if n == "short"), None)
        long = next((s for n, s in present if n == "long"), None)
        if short is not None and long is not None and short < -15 and long > 20:
            return (
                "conflicting",
                f"Short-term pullback inside a longer-term uptrend: {names}.",
            )
        if short is not None and long is not None and short > 15 and long < -20:
            return (
                "conflicting",
                f"Short-term bounce against a longer-term downtrend: {names}.",
            )
        return "conflicting", f"Short/medium/long-term trends disagree: {names}."
    return "mixed", f"Timeframes are mixed rather than fully aligned: {names}."


def _bucket(score: float) -> str:
    if score >= 20:
        return "up"
    if score <= -20:
        return "down"
    return "flat"


def synthesize(analysis: TickerAnalysis) -> TickerAnalysis:
    if analysis.error or not analysis.trends:
        analysis.headline = f"{analysis.ticker}: no trend analysis available"
        analysis.synthesis = analysis.error or "Insufficient price history to score trends."
        return analysis

    horizons = analysis.horizons or build_horizons(analysis.trends)
    analysis.horizons = horizons
    fund = analysis.fundamentals
    overall = _overall_score(analysis.trends)
    overall_label = score_label(overall) if overall is not None else "Unknown"

    headline = _headline(analysis.ticker, overall, overall_label, horizons, fund)
    analysis.headline = headline
    analysis.synthesis = _paragraphs(analysis.ticker, overall, overall_label, horizons, analysis.trends, fund)
    return analysis


def _overall_score(trends: list[PeriodTrend]) -> float | None:
    # Slightly heavier on medium/long so a noisy month does not dominate.
    horizon_weight = {"short": 0.25, "medium": 0.40, "long": 0.35}
    return weighted_mean((horizon_weight.get(t.horizon, 0.3), t.score) for t in trends)


def _headline(
    ticker: str,
    overall: float | None,
    overall_label: str,
    horizons: HorizonView,
    fund: FundamentalsSnapshot | None,
) -> str:
    fund_bit = ""
    if fund and fund.eps_trend in {"improving", "deteriorating"}:
        if overall is not None and overall >= 20 and fund.eps_trend == "deteriorating":
            fund_bit = " — price rising while earnings deteriorate"
        elif overall is not None and overall <= -20 and fund.eps_trend == "improving":
            fund_bit = " — price falling while earnings improve"
        elif fund.margin_trend == "improving" and overall is not None and overall >= 20:
            fund_bit = " with improving margins"
        elif fund.eps_trend == "improving" and overall is not None and overall >= 20:
            fund_bit = " with improving earnings"
        elif fund.eps_trend == "deteriorating":
            fund_bit = " with deteriorating earnings"

    if horizons.agreement == "conflicting":
        core = horizons.agreement_note.split(":")[0]
        return f"{ticker}: {core}{fund_bit}"
    return f"{ticker}: {overall_label.lower()} across requested windows{fund_bit}"


def _paragraphs(
    ticker: str,
    overall: float | None,
    overall_label: str,
    horizons: HorizonView,
    trends: list[PeriodTrend],
    fund: FundamentalsSnapshot | None,
) -> str:
    trend_bits = ", ".join(
        f"{t.period} {t.label.lower()} ({fmt_score(t.score)}, return {fmt_pct(t.components.total_return)})"
        for t in trends
    )
    rsi_note = _rsi_note(trends)
    structure_note = _structure_note(trends)

    p1 = (
        f"{ticker} screens as **{overall_label.lower()}** overall "
        f"(blend {fmt_score(overall)}). Period detail: {trend_bits}. "
        f"{horizons.agreement_note}"
    )
    extras = " ".join(x for x in (structure_note, rsi_note) if x)
    if extras:
        p1 = f"{p1} {extras}"

    p2 = _fundamentals_paragraph(fund)
    p3 = _readthrough(overall, horizons, fund)
    return "\n\n".join(p for p in (p1, p2, p3) if p)


def _rsi_note(trends: list[PeriodTrend]) -> str:
    # Use the shortest window's RSI as the "right now" reading.
    ordered = sorted(trends, key=lambda t: t.components.n_bars)
    rsi = ordered[0].components.rsi if ordered else None
    if rsi is None:
        return ""
    if rsi >= 70:
        return f"RSI({rsi:.0f}) on the shortest window is overbought — momentum is stretched."
    if rsi <= 30:
        return f"RSI({rsi:.0f}) on the shortest window is oversold — selling looks stretched."
    return f"RSI on the shortest window is {rsi:.0f} (neither overbought nor oversold)."


def _structure_note(trends: list[PeriodTrend]) -> str:
    # Prefer medium/long structure for the "character" of the move.
    preferred = [t for t in trends if t.horizon in {"medium", "long"}] or trends
    pick = preferred[-1]
    label = pick.components.structure_label
    if not label or label == "no clear swing structure":
        return ""
    return f"Swing structure on {pick.period}: {label}."


def _fundamentals_paragraph(fund: FundamentalsSnapshot | None) -> str:
    if fund is None:
        return "Fundamentals were not available for this ticker."
    name = fund.name or fund.ticker
    sector = f" ({fund.sector})" if fund.sector else ""
    quality = (
        f"Fundamental quality screens **{fund.quality_label.lower()}**"
        f" ({fund.quality_score:.0f}/100)."
        if fund.quality_score is not None
        else "Fundamental quality could not be scored from the available fields."
    )
    growth = []
    if fund.revenue_growth_yoy is not None:
        growth.append(f"revenue YoY {fmt_pct(fund.revenue_growth_yoy)}")
    if fund.revenue_cagr is not None:
        growth.append(f"multi-year revenue CAGR {fmt_pct(fund.revenue_cagr)}")
    if fund.earnings_growth_yoy is not None:
        growth.append(f"earnings YoY {fmt_pct(fund.earnings_growth_yoy)}")
    growth.append(f"EPS/net-income trend {fund.eps_trend}")
    growth.append(f"margin trend {fund.margin_trend}")
    growth_txt = "; ".join(growth)

    val = []
    if fund.pe_trailing is not None:
        val.append(f"trailing P/E {fund.pe_trailing:.1f}")
    if fund.pe_forward is not None:
        val.append(f"forward P/E {fund.pe_forward:.1f}")
    if fund.ps is not None:
        val.append(f"P/S {fund.ps:.1f}")
    if fund.pb is not None:
        val.append(f"P/B {fund.pb:.1f}")
    if fund.ev_ebitda is not None:
        val.append(f"EV/EBITDA {fund.ev_ebitda:.1f}")
    val_txt = ", ".join(val) if val else "limited valuation multiples"

    bal = []
    if fund.operating_margin is not None:
        bal.append(f"operating margin {fmt_pct(fund.operating_margin, signed=False)}")
    if fund.profit_margin is not None:
        bal.append(f"profit margin {fmt_pct(fund.profit_margin, signed=False)}")
    if fund.roe is not None:
        bal.append(f"ROE {fmt_pct(fund.roe, signed=False)}")
    if fund.roa is not None:
        bal.append(f"ROA {fmt_pct(fund.roa, signed=False)}")
    if fund.debt_to_equity is not None:
        bal.append(f"debt/equity {fund.debt_to_equity:.2f}x")
    if fund.free_cash_flow is not None:
        from stock_analyzer.util import fmt_compact

        bal.append(f"FCF {fmt_compact(fund.free_cash_flow)} ({fund.fcf_trend})")
    bal_txt = "; ".join(bal) if bal else "profitability/leverage fields were sparse"

    extra = ""
    if fund.notes:
        extra = " Notes: " + " ".join(fund.notes)

    return (
        f"{name}{sector}: {quality} Growth: {growth_txt}. "
        f"Valuation snapshot: {val_txt}. Profitability & balance sheet: {bal_txt}.{extra}"
    )


def _readthrough(
    overall: float | None,
    horizons: HorizonView,
    fund: FundamentalsSnapshot | None,
) -> str:
    trend_up = overall is not None and overall >= 20
    trend_down = overall is not None and overall <= -20
    eps_up = fund is not None and fund.eps_trend == "improving"
    eps_down = fund is not None and fund.eps_trend == "deteriorating"
    margins_up = fund is not None and fund.margin_trend == "improving"
    margins_down = fund is not None and fund.margin_trend == "deteriorating"
    quality_strong = fund is not None and fund.quality_score is not None and fund.quality_score >= 60
    quality_weak = fund is not None and fund.quality_score is not None and fund.quality_score < 45

    if trend_up and (eps_down or margins_down):
        return (
            "Read-through: **price rising while earnings/margins are deteriorating** — "
            "a cautionary divergence. The tape is stronger than the income statement; "
            "treat upside as less confirmed until fundamentals stabilize."
        )
    if trend_down and (eps_up or margins_up):
        return (
            "Read-through: **price is falling while fundamentals are improving** — "
            "a possible disconnect (could be a setup or a value trap). "
            "Confirm whether the longer-term trend is also turning, not just a short bounce in estimates."
        )
    if trend_up and (eps_up or margins_up or quality_strong):
        extra = ""
        if horizons.agreement == "conflicting":
            extra = " Near-term weakness looks like a pause inside a constructive longer trend, not a full regime change."
        return (
            "Read-through: **uptrend with supportive fundamentals** "
            "(growth and/or margins not working against the tape)." + extra
        )
    if trend_down and (eps_down or margins_down or quality_weak):
        return (
            "Read-through: **downtrend with weak or deteriorating fundamentals** — "
            "price and the business are rhyming to the downside."
        )
    if horizons.agreement == "conflicting":
        return (
            "Read-through: timeframes disagree, so the setup is tactical rather than one-sided. "
            "Weight the longer-term score unless you have a short-horizon mandate."
        )
    return (
        "Read-through: trend and fundamentals are not sending a sharp joint signal. "
        "Treat this as a watchlist/monitoring case rather than a one-way tape."
    )
