# Quantis — Quantitative Swing-Trading Dashboard ($100 account)

**Date:** 2026-07-30
**Status:** Approved (platform, data source, universe, and fractional-share decisions confirmed).

## Purpose

A local Streamlit dashboard that helps the user deploy a $100 account on a 1–7 day
swing-trading horizon, quantitatively: live market data, a signal-driven trade-idea
scanner, a strategy backtester, Markowitz portfolio optimization, and CAPM risk
metrics (alpha, beta, Sharpe, Sortino, VaR, drawdown) plus a paper-portfolio tracker.

Constraints and decisions (user-confirmed):

- **Platform:** Streamlit web app running locally, Python 3.12.
- **Data:** yfinance (free, no key; quotes ~1–2 min delayed; daily + intraday history).
- **Universe:** ~60 curated liquid movers (mega-tech, semis, high-beta names,
  index + leveraged ETFs) with SPY as benchmark. User can edit the list in code.
- **Sizing:** fractional shares — the optimizer outputs exact dollar allocations.
- **Honesty:** the app maximizes *expected* return; it must state that short-horizon
  profits cannot be guaranteed. Educational, not financial advice.

## Architecture

Modular package with a UI-free quant core (testable with pytest) and a thin Streamlit UI:

```
app.py                  # Streamlit UI, 5 tabs
src/quantis/universe.py    # ticker universe + benchmark
src/quantis/data.py        # yfinance download, caching, quote table
src/quantis/indicators.py  # RSI, EMA, MACD, ATR, Bollinger %B, ADX, ROC, rel. volume
src/quantis/signals.py     # composite Quantis Score + trade-idea construction
src/quantis/backtest.py    # vectorized backtester + built-in strategies + stats
src/quantis/optimize.py    # mean-variance optimizer, efficient frontier
src/quantis/risk.py        # beta, alpha, Sharpe, Sortino, VaR, max DD, correlations
src/quantis/portfolio.py   # paper portfolio persisted to portfolio.json
tests/                  # pytest suite for the quant core
```

Data flow: `data.py` produces tidy OHLCV panels (DataFrame indexed by date, columns
per ticker) → indicators/signals/backtest/optimize/risk all consume those panels →
`app.py` renders results. Streamlit `st.cache_data(ttl=300)` caches downloads;
a Refresh button clears cache for near-real-time updates.

## Components

### 1. Market Dashboard tab
Quote table (last, day %, 5d %, relative volume), daily-move heatmap (treemap),
SPY/QQQ/IWM context sparkline. Data: 1y daily bars + latest quotes.

### 2. Trade Ideas tab (real-time suggestions)
Composite **Quantis Score** per ticker = weighted z-score blend of:
momentum (5/10/20d ROC), mean-reversion (RSI-2, Bollinger %B) gated by trend filter
(price vs EMA-20/50, MACD histogram, ADX), and relative volume confirmation.
Output: ranked table; top-5 cards with entry (last price), ATR(14)-based stop
(entry − 1.5·ATR), target (entry + 2×risk), suggested hold 1–7 days, and suggested
dollar slice of the $100 (Quantis-Score-weighted, blended with optimizer weights,
25% per-name cap). Disclaimer banner.

### 3. Backtester tab
Vectorized daily engine over the universe. Strategies: cross-sectional momentum
(top-N by k-day ROC, hold h days), RSI-2 mean reversion (entry RSI2 < X in uptrend,
exit RSI2 > Y or h days), MACD crossover, Bollinger reversion, SPY buy-&-hold
benchmark. User parameters: date range, lookback, top-N, holding period, stop-loss %,
slippage bps, starting capital ($100 default). Outputs: equity curve vs SPY, total
return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor, trade count,
and the strategy's alpha/beta vs SPY. Signals are computed on close t and positions
entered at close t (market-on-close), earning returns from t onward — no look-ahead.

### 4. Portfolio Optimizer tab
Inputs: selected tickers (default: top Quantis-Score names), lookback window (default 1y).
Expected returns: exponentially weighted mean daily returns, annualized. Covariance:
Ledoit-Wolf shrinkage (sklearn). Solver: scipy SLSQP — max-Sharpe and min-variance,
long-only, weights sum to 1, 40% single-name cap. Outputs: weight bars, exact dollar
allocation of $100, portfolio expected return / vol / Sharpe, efficient frontier plot
with both portfolios and individual assets marked.

### 5. Risk & Tracking tab
Per-ticker table: CAPM beta and annualized Jensen's alpha vs SPY, Sharpe, Sortino,
annualized vol, 95% 1-day historical VaR, max drawdown. Correlation heatmap.
Paper portfolio: add/remove positions (ticker, shares, cost basis) persisted to
`portfolio.json`; live P&L, portfolio beta/alpha/vol vs SPY.

## Error handling

- yfinance failures / empty frames: drop the ticker, surface a warning chip, never crash.
- Optimizer infeasibility (e.g. all-negative expected returns): fall back to
  min-variance and label the fallback.
- Insufficient history (< 60 trading days): exclude ticker from optimization/risk.
- No internet: cached data if present, else a clear error banner.

## Testing

Pytest over the quant core with synthetic price series: indicator correctness
(RSI bounds, ATR positivity, known MACD values), backtest accounting (no look-ahead,
costs applied, benchmark math), optimizer invariants (weights sum to 1, respect cap,
min-variance vol ≤ equal-weight vol), risk metrics (beta of SPY vs itself = 1,
VaR sign, drawdown ≤ 0).

## Out of scope

Broker integration / order execution, options, intraday tick data, alerting/notifications,
multi-user auth. The paper tracker stands in for execution.
