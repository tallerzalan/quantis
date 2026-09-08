# Quantis overhaul — design

Date: 2026-09-07
Status: approved

## Goal

Turn Quantis into a minimalist **Bloomberg-terminal-style fintech dashboard**,
deepen the quant engine (factors, sectors, better risk models, Black-Litterman,
more indicators), and upgrade data visualization — while keeping it a local,
single-user tool. Work is cost-conscious: high impact, no wasteful token spend.

## Aesthetic direction

- Minimalist terminal: denser information, quiet surfaces, thin dividers,
  monospace tabular numerics, sharp accent use. Remove decorative gradients.
- Rebrand `EDGE` → **QUANTIS** wordmark + small geometric mark.
- Keep the existing validated CVD-safe dark palette (migrate into Tailwind theme).
- `⌘K` command palette for ticker search + navigation.

## Frontend foundation

- Add **Tailwind CSS v4** + **shadcn/ui** primitives + **MagicUI** accents
  (installed via the shadcn CLI/registry — no MCP required).
- Coexist with existing `index.css` (compatibility layer) to avoid a risky,
  token-expensive full rewrite of all 8 pages. Restyle shell + high-impact
  surfaces + all new components with the new system.
- MagicUI used sparingly: animated number tickers (prices/P&L), load shimmer,
  a subtle dot-grid behind the header only.

## New quant capabilities (Python core, tested + plain-English verdicts)

- `factors.py` (new): factor-model regression vs ETF proxies (market SPY, size,
  value, momentum, quality) → per-ticker & portfolio factor betas + R².
- Sector exposure: map tickers→sector via yfinance; aggregate portfolio weights.
- `risk.py`: CVaR / expected shortfall, rolling beta, downside beta,
  Cornish-Fisher VaR, Calmar & Omega ratios.
- `indicators.py`: VWAP, Stochastic, OBV, Keltner channels, ATR trailing stop,
  Ichimoku (subset).
- `optimize.py`: **Black-Litterman** portfolio (market-implied prior + views),
  alongside existing Markowitz mixes.

## Data-visualization upgrades

- Today: per-row sparklines, regime gauge, market-breadth bar.
- Risk: upgraded correlation heatmap, rolling-beta line, underwater drawdown
  curve, risk/return scatter (bubble = position size).
- Optimize: efficient-frontier scatter with the portfolios plotted, allocation
  donut; Black-Litterman inputs/outputs.
- New **Factors** page: factor-exposure bars + sector-allocation donut.

## Build phases

1. Foundation — Tailwind + shadcn + MagicUI, rebrand, token migration, ⌘K.
2. Quant core — factors, sectors, risk, indicators, Black-Litterman + tests + API.
3. Dataviz — new charts per page + Factors page wired to new APIs.
4. Polish & verify — run app, Chrome DevTools MCP screenshots, iterate.

## Verification

- `python -m pytest tests -q` stays green (+ new tests).
- `cd frontend; npm run build` succeeds.
- App runs; each page visually verified in a real browser.

## Non-goals

- Multi-user, auth, deployment, live brokerage. Stays local & single-user.
