# Terminal analytics: significant moves, forecasts, and Monte Carlo — design

Date: 2026-08-05
Status: approved

## Goal

Bring three Bloomberg-terminal-style capabilities to Quantis, in its existing
plain-English, consumer-friendly voice:

1. **Why it moved** — on any historical chart, detect statistically
   significant daily moves (like PLTR's +30% earnings pop), mark them on the
   chart, and explain each one: how rare the move was, what the likely
   catalyst was (earnings / news / split / market-wide), and whether volume
   confirmed it.
2. **When to buy** — a prediction of the next best time to buy a ticker,
   built for the app's core strategy: buy low, sell high, 1–7 day swings.
3. **Monte Carlo lab** — simulate thousands of possible price futures from
   real historical returns, show the fan of outcomes, and stress-test the
   buy-the-dip strategy (and any entry the app recommends) against them.

## Decisions and rationale

- **Data stays free (yfinance only).** No API keys. Consequences:
  - Headlines are only available for roughly the last few weeks
    (`Ticker.news`). Older significant moves are explained by earnings dates
    (`get_earnings_dates`), dividends/splits (`Ticker.actions`), and
    market-wide co-movement vs SPY. When nothing matches we say so honestly:
    "no identified catalyst".
  - This was chosen over Finnhub/AlphaVantage free tiers because those need
    keys and have tight rate limits; a future `NEWS_API_KEY` hook can extend
    coverage without changing the design.
- **Significance = return vs its own recent volatility.** A day's move is
  measured as a z-score against the EWMA standard deviation of daily returns
  *up to the prior day* (span 21, shifted one day so a spike never dampens its
  own significance). Default threshold |z| ≥ 2.5 (~1.2% two-sided under a
  normal). We report the p-value as an odds phrase ("a move this size happens
  by chance about 1 day in 80") and note the bell-curve assumption, since real
  returns have fat tails.
- **Monte Carlo = circular block bootstrap of real daily returns** (block 5,
  default 2,000 paths × 21 sessions). Resampling real returns keeps fat tails
  and skew that a GBM/normal simulation would erase — the right default for a
  tool that must be honest about tail risk. Seeded deterministically per
  (ticker, latest bar) so results don't jitter on every reload.
- **"Next best time to buy" is probabilistic, not a date.** From the
  simulated paths we derive: the distribution of when each path hits its low,
  the median low price, the probability of a dip of X% within the horizon,
  and a dip-buy strategy test (buy at −X% limit, sell at +Y% target,
  stop at −Z%, timeout at horizon) compared head-to-head against buying
  today. The UI phrases it as a plan: "set a limit at $A — it fills in ~B% of
  futures, usually within C sessions; if it hasn't filled by then, reassess."
  An earnings date inside the horizon triggers an explicit event-risk warning.
- **All math is pure and tested in `src/quantis/`;** yfinance calls live in
  `data.py`; sentences live in `interpret.py`; endpoints stay thin.

## Approaches considered

- *Event detection:* fixed %-move threshold (rejected: 5% is huge for KO,
  noise for a small cap) vs z-score vs own volatility (chosen) vs GARCH
  (rejected: complexity without user-visible benefit).
- *Simulation:* GBM (rejected: thin tails, understates risk), IID bootstrap
  (ok but loses short-run autocorrelation), block bootstrap (chosen).
- *News:* paid/keyed APIs (rejected for now) vs yfinance + earnings calendar
  + market decomposition (chosen).

## Components

### `src/quantis/events.py` (new, pure)
- `move_significance(close, volume, z_thresh=2.5, span=21) -> DataFrame` —
  columns `ret, z, pvalue, rvol` for days beyond the threshold.
- `attribute_events(events, index, earnings_dates, actions, news, bench_close)`
  → list of dicts adding `direction, market_move, bench_ret, catalyst
  (earnings|split|dividend|news|market|unknown), headlines`.
  Priority: earnings (event day or next session) > split/dividend (ex-date) >
  news (±36 h) > market-wide (same-sign SPY z ≥ 1.5) > unknown.

### `src/quantis/montecarlo.py` (new, pure)
- `simulate_paths(returns, horizon=21, n_paths=2000, block=5, seed)` →
  growth-factor array, shape `(n_paths, horizon+1)`, col 0 = 1.0.
- `fan_bands(paths, last_price)` → per-day P5/P25/P50/P75/P95.
- `summarize(paths)` → prob_up, expected return, end-value percentiles.
- `dip_probabilities(paths, dips)` → chance the path low reaches each dip.
- `best_entry(paths)` → distribution of the low's timing + median low.
- `dip_buy_outcomes(paths, dip, target, stop)` → fill rate, win rate,
  average return (filled and overall), median sessions-to-fill, and the same
  target/stop applied from day 0 ("buy today") for comparison.

### `src/quantis/interpret.py` (extend)
- `odds_phrase(pvalue)`, `event_story(ev)` — the plain-English explanation.
- `entry_verdict(...)` — Buy zone / No rush / Wait: blends current dip
  context (RSI, %B, distance from highs) with simulated dip odds.
- `forecast_narrative(...)` — one honest paragraph per forecast, plus the
  standing caveat that these are odds from history, not promises.

### `src/quantis/data.py` (extend, network, all guarded to return empties)
- `earnings_dates(ticker)`, `corporate_actions(ticker)`, `recent_news(ticker)`
  (handles both old flat and new `content`-nested yfinance news shapes).

### `server.py` (extend)
- `GET /api/events/{ticker}?period=&z=` → events (newest first) with stories
  and chart markers; catalyst lookups cached 1 h.
- `GET /api/forecast/{ticker}?period=&horizon=&dip=&target=&stop=` → fan
  bands on future business days, summary, dip odds, best-entry, strategy
  comparison, entry verdict + plan, next earnings date, narrative.

### Frontend
- **ChartPage**: markers on the candles (▲/▼ at significant days) via
  lightweight-charts v5 `createSeriesMarkers`, plus a "Why it moved" card
  listing each event: date, move, rarity, catalyst chip, story, headline
  links.
- **New Forecast page** (nav between Charts and Backtest): SVG fan chart
  (60 d history + P5–P95 / P25–P75 bands + median), outcome tiles
  (chance higher, expected path, 1-in-20 bad case), "When to buy" plan card,
  dip-buy strategy tester with adjustable dip/target/stop and an outcome
  histogram, event-risk warning, disclaimer.

## Error handling
- Empty/short history → 404/422 with plain messages (existing pattern).
- All catalyst fetches degrade silently to "unknown catalyst".
- `clean()` keeps every payload JSON-safe.

## Testing
`tests/test_events_forecast.py`, synthetic series only (no network):
injected-jump detection & attribution priority, market vs stock-specific
classification, bootstrap shape/seed/percentile invariants, drift → prob_up
sanity, deterministic dip-buy accounting (fill/win/timeout), best-entry on
crafted paths, odds/verdict phrasing bounds.
