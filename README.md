# Stock analyzer

CLI (and optional local web UI) that scores **price trends across multiple timeframes** and combines them with **company fundamentals** into a readable report.

Default demo tickers are `AAPL TSLA HD ETN VRT VST NAGE` (a sample US equity holdings list). Any US equity ticker Yahoo Finance knows will work.

> **Disclaimer:** This is analysis tooling for education and research. It is **not investment advice**, not a recommendation to buy or sell, and not a substitute for your own due diligence. Data can be wrong or delayed. Past returns do not predict future results.

## Install

Python 3.10+ recommended.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Or with a plain requirements file:

```bash
pip install -r requirements-dev.txt
pip install -e .
```

No API key is required. Price and fundamentals come from [Yahoo Finance](https://finance.yahoo.com/) via [`yfinance`](https://github.com/ranaroussi/yfinance). If Yahoo rate-limits or blocks your network, rerun later; tests never hit the network.

There is **no brokerage integration** and the app **does not place trades**. Interactive Brokers is not connected; the demo list is just tickers.

## Run

```bash
# Demo holdings, default periods 1mo,3mo,6mo,1y,5y
python -m stock_analyzer

# Explicit tickers and periods
python -m stock_analyzer AAPL TSLA --periods 1mo,3mo,6mo,1y,5y

# Markdown + HTML + per-period PNG charts
python -m stock_analyzer AAPL HD --periods 1mo,1y,5y \
  --output report.md --html report.html --charts-dir charts

# Local web UI (127.0.0.1:8000)
python -m stock_analyzer --web
```

Equivalent console script after install: `stock-analyzer AAPL TSLA`.

### CLI flags

| Flag | Meaning |
| --- | --- |
| `tickers` | Optional. Default: AAPL TSLA HD ETN VRT VST NAGE |
| `--periods` | Comma-separated: `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y` |
| `-o` / `--output` | Write Markdown (stdout always prints the report) |
| `--html` | Self-contained HTML (overview chart embedded) |
| `--json` | Machine-readable dump |
| `--charts-dir` | PNG of price + SMAs for **each ticker and period** |
| `--web` | Local UI; `--host` / `--port` to bind |

## What the score is

Each ticker × period gets a trend score from **-100 to +100**. The report prints the method in full; the short version:

1. **Return (30%)** — total return in the window, tanh-scaled so a “strong” move for that horizon is near ±100 (1mo ~12%, 1y ~35%, 5y ~120%).
2. **MA alignment (25%)** — close vs SMA_fast vs SMA_slow (e.g. 20/50 on 3–6mo, 50/200 on 5y). Price > fast > slow is fully bullish.
3. **MA slope (20%)** — linear-regression slope of the fast SMA, as implied percent change, same tanh scale.
4. **Structure (15%)** — swing highs/lows: higher-highs & higher-lows vs lower-highs & lower-lows.
5. **Momentum (10%)** — RSI(14) and MACD histogram as supporting context (overbought/oversold tags). This slice cannot produce a “strong” label by itself.

Missing pieces (new listings, no SMA200 yet) are dropped and the other weights renormalize.

Horizons: **1mo/3mo = short**, **6mo/1y = medium**, **2y/5y/10y = long**. Those three can disagree; the report says so (for example a short-term pullback inside a long-term uptrend).

Fundamentals (revenue growth, EPS/net-income trend, margins, PE/PS/PB, EV/EBITDA, debt/equity, FCF, ROE/ROA) are scored into a 0–100 **quality** heuristic and then **synthesized** with the tape: e.g. “uptrend with improving margins” vs “price rising while earnings deteriorating”.

## Example

Checked-in sample (offline fixture data, so CI does not need Yahoo):

- [`examples/sample_report.md`](examples/sample_report.md)
- [`examples/sample_report.html`](examples/sample_report.html)

Regenerate it with:

```bash
python examples/generate_sample.py
```

Excerpt from the checked-in synthetic sample (`examples/sample_report.md`):

```
## Cross-ticker scoreboard

| Ticker | 1mo | 3mo | 6mo | 1y  | 5y  | Quality       | Headline                                                                    |
| ------ | --- | --- | --- | --- | --- | ------------- | --------------------------------------------------------------------------- |
| ACME   | +59 | +71 | +80 | +88 | +90 | Strong (82)   | ACME: strong uptrend across requested windows with improving margins        |
| FADE   | -39 | -58 | -64 | -74 | -73 | Stressed (15) | FADE: strong downtrend across requested windows with deteriorating earnings |
| CHOP   | +57 | +62 | +31 | +4  | +17 | —             | CHOP: uptrend across requested windows                                      |
```

Live Yahoo numbers change every session. After install you can run:

```bash
python -m stock_analyzer AAPL TSLA --periods 1mo,3mo,6mo,1y,5y
```

## Project layout

```
stock_analyzer/
  cli.py            # python -m stock_analyzer
  analyze.py        # orchestration
  data.py           # yfinance adapter (+ in-memory FixtureProvider)
  trend.py          # indicators + period scores (pure, no I/O)
  fundamentals.py   # statements + quality heuristic
  synthesis.py      # qualitative headline + multi-period agreement
  report.py         # Markdown / HTML
  charts.py         # matplotlib PNG (price + SMAs)
  web.py            # stdlib local UI
tests/              # fixtures only — no live network
examples/
```

## Tests

```bash
pytest
```

Trend, scoring, fundamentals, synthesis, and report tests use synthetic OHLCV and statement fixtures. They do not download market data.

## Optional keys / other data

None required. There is no paid-API path in this repo. If you later swap `YahooFetcher` for another `MarketDataProvider`, keep tests on `FixtureProvider`.
