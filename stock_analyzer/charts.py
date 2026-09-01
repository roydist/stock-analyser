"""PNG charts of price plus moving averages for a scored period."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from stock_analyzer.config import PERIODS
from stock_analyzer.trend import add_indicators


def plot_period(
    history: pd.DataFrame,
    ticker: str,
    period: str,
    *,
    dest: Path | None = None,
) -> bytes:
    cfg = PERIODS[period]
    indicated = add_indicators(history) if "SMA_20" not in history.columns else history
    window = indicated.iloc[-cfg.bars :] if len(indicated) > cfg.bars else indicated
    close = window["Close"]
    fast_col = f"SMA_{cfg.sma_fast}"
    slow_col = f"SMA_{cfg.sma_slow}"

    fig, ax = plt.subplots(figsize=(10, 4.6), dpi=120)
    ax.plot(window.index, close, color="#1f77b4", linewidth=1.6, label="Close")
    if fast_col in window.columns:
        ax.plot(window.index, window[fast_col], color="#ff7f0e", linewidth=1.2, label=f"SMA {cfg.sma_fast}")
    if slow_col in window.columns:
        ax.plot(window.index, window[slow_col], color="#2ca02c", linewidth=1.2, label=f"SMA {cfg.sma_slow}")
    ax.set_title(f"{ticker} — {period} price + moving averages")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    data = buf.getvalue()
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data


def export_charts(
    histories: dict[str, pd.DataFrame],
    periods: list[str],
    dest_dir: Path,
    *,
    overview_only: bool = False,
) -> dict[str, str]:
    """Write PNGs; return map of keys -> relative path strings.

    Keys are ``TICKER:period`` and ``TICKER`` (longest period overview).
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    longest = max(periods, key=lambda p: PERIODS[p].bars)
    for ticker, history in histories.items():
        if history is None or history.empty:
            continue
        overview = dest_dir / f"{ticker}_{longest}.png"
        plot_period(history, ticker, longest, dest=overview)
        paths[ticker] = str(overview)
        if overview_only:
            continue
        for period in periods:
            path = dest_dir / f"{ticker}_{period}.png"
            plot_period(history, ticker, period, dest=path)
            paths[f"{ticker}:{period}"] = str(path)
    return paths


def png_to_data_uri(png: bytes) -> str:
    b64 = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{b64}"
