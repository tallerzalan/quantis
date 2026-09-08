# Quantis — quantitative clarity for every trade

**Quantis** is a local, browser-based quantitative trading terminal for
small accounts (default **$100**) on a **1–7 day swing horizon**. It runs a
real quant stack — signal scoring, event attribution, Monte Carlo forecasting,
strategy backtesting, Markowitz optimization, and CAPM risk — on free Yahoo
Finance data, and translates **every single number into a plain-English
verdict**. You never have to already know what a Sharpe ratio is to use it.

React + Framer Motion frontend · Python quant core · FastAPI · yfinance.

---

## Why Quantis exists

Serious quantitative tooling is either **locked inside institutions** (Bloomberg
terminals, in-house risk engines) or **scattered across intimidating libraries**
that assume you already speak the language of factors, covariance shrinkage, and
value-at-risk. Retail traders are left with two bad options: gut-feel apps that
show a price and a green/red arrow, or raw spreadsheets that show a number with
no interpretation.

Quantis closes that gap. It is built on three convictions:

- **Small accounts deserve real math.** Position sizing, expected-return ranking,
  stop placement, and portfolio optimization matter *more* when every dollar
  counts — not less. Quantis sizes trades and splits capital to the exact dollar.
- **A number without a verdict is noise.** Beta `1.4`, RSI `73`, VaR `-4.2%` mean
  nothing on their own. Quantis attaches a one-sentence, jargon-free reading to
  each one ("moves ~40% more than the market," "overbought," "a normal bad day
  loses about 4%").
- **Honesty over hype.** Short-horizon trading cannot be guaranteed. Quantis
  maximizes *expected* return, states its own assumptions, marks its confidence,
  and always shows the downside next to the upside.

The result is a tool that is genuinely useful to a beginner on day one, and
still rigorous enough to trust for real capital allocation.

---

## Get it from GitHub

Clone the repo and enter it:

```bash
git clone https://github.com/nmamzada/quantis.git
cd quantis
```

Install dependencies (needs **Python 3.10+** and **Node.js 18+**):

```bash
pip install -r requirements.txt      # Python quant core + server
cd frontend && npm install && npm run build && cd ..   # build the UI once
```

Then launch it:

```bash
python serve.py
```

Your browser opens at http://127.0.0.1:8000.

> On Windows PowerShell, replace `&&` with `;` (e.g. `cd frontend; npm install; npm run build; cd ..`).

## Run it

Once installed, a single command starts everything:

```bash
python serve.py
```

That's it — your browser opens at http://127.0.0.1:8000.

First-time setup (once):

```bash
pip install -r requirements.txt
```

To rebuild the UI after changing anything under `frontend/`:

```powershell
cd frontend; npm install; npm run build
```

---

## What's inside — every functionality

Quantis is organized into nine sections. Hit **⌘K / Ctrl-K** anywhere to open the
**command palette** — search any ticker on Yahoo Finance or jump to any section
instantly. Added tickers land in your watchlist, and every section — ideas,
factors, backtests, optimizer, risk — updates to include them. The `×` on a chip
removes it.

### 📊 Today — market at a glance
- **Market regime** classifier (Risk-on / Mixed / Risk-off), each explained in a
  single sentence, derived from index breadth and momentum.
- Index tiles (SPY / QQQ / IWM) and the day's **biggest movers**.
- Your entire watchlist **ranked by the Quantis Score** (0–100 composite), with a
  color-coded, plain-English read on each.

### 💡 Ideas — ready-to-trade setups
- The **top-5 trade setups** for your capital, sized to your account.
- Each idea ships with: **entry, stop, target, expected hold time, dollar risk,**
  and a **one-sentence rationale** ("strong uptrend, pulling back into support").
- A **full ranking table** of every watchlist ticker by Quantis Score.

### 📈 Charts — interpreted candlestick explorer
For **any** Yahoo ticker:
- Candlesticks with **EMA 20/50**, plus toggleable **Bollinger Bands, RSI, and
  MACD** panes.
- **Volume** with a moving average and **unusual-volume bar highlighting**.
- **Interpreted signal readouts** — e.g. "RSI 73 · overbought," "MACD crossing up."
- A plain-English **fact sheet** per ticker for non-quant readers: company size,
  P/E, dividend, 52-week position, typical daily move, liquidity, and beta — each
  with a note on what it means.
- **CAPM verdicts** (how it moves relative to the market).
- **"Why it moved"** — statistically significant days (**≥ 2.5σ** vs the stock's
  *own* volatility) are marked on the chart and **explained on hover**: how rare
  the move was, the likely catalyst (**earnings / split / dividend / headlines /
  market-wide co-move**, with an honest "unknown" when there's no clear cause),
  and whether **volume confirmed** it — with linked headlines where available.

### 🔮 Forecast — Monte Carlo lab
- **2,000 simulated futures** built from the stock's *real* historical returns via
  **circular block bootstrap** (preserving short-term autocorrelation).
- **Volatility-regime aware**: returns are rescaled to *today's* volatility by
  default (EWMA sigma), with a toggle for the full-year mix.
- **Fan chart** of outcomes, **chance-higher odds**, and the **worst 1-in-20** case.
- A **when-to-buy verdict** with a concrete **limit-order plan** (limit price, fill
  odds, time window, earnings warning).
- A **buy-the-dip vs. buy-today** strategy tester.
- A full **"how it's computed" parameter line** (paths, blocks, sample size, vol
  regime, fat-tail stats) — nothing hidden.

### 🧩 Factors — what actually drives your watchlist
- **Factor-model regression** of every ticker against liquid ETF proxies for the
  **market, size, value, momentum, quality, and low-volatility** factors —
  recovering each name's factor betas, its selection **alpha**, and **R²** (how
  much of its movement the factors explain).
- A **watchlist-level factor-exposure** bar chart with a one-line plain-English
  read ("moves ~1.4× with the market, tilts toward small-caps…").
- A **sector-allocation donut** (which sectors you're really concentrated in) with
  a concentration verdict.

### 🧪 Backtest — strategy lab
- **9 built-in strategies**: momentum, RSI-2 dip, MACD, Bollinger, breakout,
  golden cross, 52-week high, gap reversal, volume surge.
- **Write your own** in a Python code editor (see below).
- Run on your **watchlist** or a **sector basket** (Semis, Mega Tech, Fintech, …).
- Results **graded A–F**, then **stress-tested with a 1,000-run Monte Carlo
  robustness check**: chance of loss, chance of beating SPY, and realistic
  best/worst final account values.

### ⚖️ Optimize — portfolio construction
- **Markowitz mean-variance optimization**: Cautious / Balanced / Bold mixes
  spanning **minimum-variance → maximum-Sharpe**.
- **Black-Litterman ("Anchored") portfolio** — starts from the returns the market's
  own weights imply (the equilibrium prior), then tilts them with Quantis's
  expected-return views, so the mix stays anchored to the market instead of
  chasing noisy estimates.
- **Ledoit-Wolf covariance shrinkage** for stable estimates on short histories.
- **Efficient-frontier map** (with each ready-made mix plotted) and the **exact
  dollar split** of your capital.

### 🛡️ Risk — know your downside
- Per-ticker **beta, downside-beta, alpha, Sharpe, Sortino, Calmar, volatility,
  VaR, expected shortfall (CVaR), and max drawdown** — each with a color-coded,
  plain-English verdict.
- A **risk/reward scatter** (return vs volatility, sized and colored by Sharpe).
- A **rolling-beta line** and **underwater drawdown curve** for any ticker.
- A **correlation heatmap** so you can see how concentrated your basket really is.

### 💼 Portfolio — paper-trading tracker
- **Buy/sell at live prices**, track **P&L**.
- **Portfolio-level beta and alpha**, plus a plain-English **worst-day estimate**.

---

## Custom strategies

In **Backtest → "Code your own"**, define a `strategy` function:

```python
def strategy(data, ind):
    close = data["close"]                      # dates x tickers DataFrame
    entries = (ind.rsi(close, 14) < 30) & (close > ind.ema(close, 50))
    exits = ind.rsi(close, 14) > 60
    return entries, exits
```

`ind` exposes `rsi, ema, macd, atr, roc, bollinger_percent_b, adx,
relative_volume, vwap, stochastic, obv, keltner_channels, atr_trailing_stop,
ichimoku`. Stops, max-hold, and position caps from the form still apply on top of
your entry/exit logic.

---

## Architecture

```
serve.py              # one-command launcher
server.py             # FastAPI: /api/* + serves frontend/dist
src/quantis/          # UI-free quant core (61 pytest tests)
  data.py             # yfinance panels + live quotes + earnings/news/actions
  indicators.py       # vectorized technical indicators (RSI, MACD, VWAP, Ichimoku…)
  signals.py          # composite Quantis Score + trade ideas
  factors.py          # factor-model regression + sector allocation
  events.py           # significant-move detection + catalyst attribution
  montecarlo.py       # block-bootstrap simulation, dip odds, entry timing
  backtest.py         # rebalance + event-loop engines, stats
  strategies.py       # built-in strategy registry
  custom.py           # user-code strategy runner (sandboxed)
  optimize.py         # Markowitz + Black-Litterman (SLSQP, Ledoit-Wolf), frontier
  risk.py             # CAPM beta/alpha, CVaR, rolling/downside beta, Calmar, VaR
  interpret.py        # plain-English verdicts for every metric
  portfolio.py        # paper portfolio (portfolio.json)
  watchlist.py        # user watchlist (watchlist.json)
frontend/             # React 19 + Tailwind + shadcn/ui + MagicUI + Recharts
docs/specs/           # design specifications
```

Testing:

```powershell
python -m pytest tests -q        # quant core tests (61)
cd frontend; npm run build       # rebuild UI after frontend changes
```

---

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | React 19, Tailwind CSS, shadcn/ui, MagicUI, Recharts, lightweight-charts, Framer Motion, Vite |
| Backend | FastAPI, Uvicorn |
| Quant core | NumPy, pandas, SciPy, scikit-learn (Ledoit-Wolf) |
| Data | yfinance (free, no API key) |

---

> ⚠️ **Educational tool, not financial advice.** Quantis maximizes *expected*
> return — no strategy can guarantee profit over 1–7 days. Stops cap the damage
> when trades lose, and losing trades are a normal part of any real strategy.
> Trade with money you can afford to lose.
