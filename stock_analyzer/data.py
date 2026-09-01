"""Market data providers. Default path is Yahoo Finance via yfinance (no API key)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import pandas as pd

from stock_analyzer.config import yfinance_fetch_period


class MarketDataProvider(Protocol):
    def history(self, ticker: str, periods: list[str]) -> pd.DataFrame:
        """OHLCV indexed by timestamp with at least a Close column."""

    def fundamentals_bundle(self, ticker: str) -> FundamentalsBundle:
        ...


@dataclass
class FundamentalsBundle:
    info: dict[str, Any] = field(default_factory=dict)
    income_annual: pd.DataFrame = field(default_factory=pd.DataFrame)
    income_quarterly: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow_annual: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_annual: pd.DataFrame = field(default_factory=pd.DataFrame)


def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [str(col[0]) for col in out.columns]
    # Keep Adj Close distinct if present; prefer Close.
    mapped = {}
    for col in out.columns:
        key = str(col).strip().lower().replace(" ", "")
        if key in {"open", "high", "low", "close", "volume"}:
            mapped[col] = key.title() if key != "volume" else "Volume"
        elif key in {"adjclose", "adj_close"}:
            mapped[col] = "Adj Close"
    out = out.rename(columns=mapped)
    if "Close" not in out.columns and "Adj Close" in out.columns:
        out["Close"] = out["Adj Close"]
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "Close" not in out.columns:
        raise ValueError("History is missing a Close column.")
    out = out.dropna(subset=["Close"]).sort_index()
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    return out


def _retry(fn, attempts: int = 3, delay: float = 1.0):
    last_exc: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — network clients raise many types
            last_exc = exc
            if i == attempts - 1:
                break
            time.sleep(delay * (i + 1))
    raise last_exc  # type: ignore[misc]


class YahooFetcher:
    """Live Yahoo Finance access through yfinance. No API key required."""

    def __init__(self) -> None:
        self._history_cache: dict[tuple[str, str], pd.DataFrame] = {}
        self._fund_cache: dict[str, FundamentalsBundle] = {}

    def history(self, ticker: str, periods: list[str]) -> pd.DataFrame:
        yf_period = yfinance_fetch_period(periods)
        cache_key = (ticker.upper(), yf_period)
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        import yfinance as yf

        def _download() -> pd.DataFrame:
            ticker_obj = yf.Ticker(ticker)
            # auto_adjust=True (yfinance default) gives split/dividend-adjusted Close.
            hist = ticker_obj.history(period=yf_period, auto_adjust=True, actions=False)
            return normalize_history(hist)

        df = _retry(_download)
        if df.empty:
            raise ValueError(f"No price history returned for {ticker}.")
        self._history_cache[cache_key] = df
        return df

    def fundamentals_bundle(self, ticker: str) -> FundamentalsBundle:
        key = ticker.upper()
        if key in self._fund_cache:
            return self._fund_cache[key]

        import yfinance as yf

        def _pull() -> FundamentalsBundle:
            t = yf.Ticker(ticker)
            info: dict[str, Any] = {}
            try:
                info = dict(t.info or {})
            except Exception:
                try:
                    info = dict(getattr(t, "fast_info", {}) or {})
                except Exception:
                    info = {}
            return FundamentalsBundle(
                info=info,
                income_annual=_safe_frame(getattr(t, "income_stmt", None)),
                income_quarterly=_safe_frame(getattr(t, "quarterly_income_stmt", None)),
                cashflow_annual=_safe_frame(getattr(t, "cashflow", None)),
                balance_annual=_safe_frame(getattr(t, "balance_sheet", None)),
            )

        bundle = _retry(_pull)
        self._fund_cache[key] = bundle
        return bundle


def _safe_frame(value: Any) -> pd.DataFrame:
    if value is None:
        return pd.DataFrame()
    if isinstance(value, pd.DataFrame):
        return value
    try:
        return pd.DataFrame(value)
    except Exception:
        return pd.DataFrame()


class FixtureProvider:
    """In-memory provider for tests and offline example generation."""

    def __init__(
        self,
        histories: dict[str, pd.DataFrame],
        fundamentals: dict[str, FundamentalsBundle] | None = None,
    ) -> None:
        self._histories = {k.upper(): normalize_history(v) for k, v in histories.items()}
        self._fundamentals = {k.upper(): v for k, v in (fundamentals or {}).items()}

    def history(self, ticker: str, periods: list[str]) -> pd.DataFrame:
        key = ticker.upper()
        if key not in self._histories:
            raise ValueError(f"No fixture history for {ticker}.")
        return self._histories[key]

    def fundamentals_bundle(self, ticker: str) -> FundamentalsBundle:
        key = ticker.upper()
        return self._fundamentals.get(key, FundamentalsBundle(info={"symbol": key}))
