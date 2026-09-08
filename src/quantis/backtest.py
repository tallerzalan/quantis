"""Backtesting engines and performance statistics.

Two engines share the same stats:
  run_rebalance      - vectorized periodic rebalance into top-N ranked names
                       (cross-sectional momentum). Weights decided at close t
                       earn returns from t to t+1 (weights are shifted; no
                       look-ahead).
  run_signal_trades  - daily event loop for entry-signal strategies (RSI-2
                       reversion, MACD cross, Bollinger reversion) with
                       ATR/percent stops, timeouts, and exit signals. Entries
                       and signal exits fill at the close the signal fires;
                       stops fill at the stop price (or the open on a gap).
Slippage is charged in basis points per side.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import indicators as ind

TRADING_DAYS = 252


# ---------------------------------------------------------------- statistics

def max_drawdown(equity: pd.Series) -> float:
    dd = equity / equity.cummax() - 1
    return float(dd.min()) if len(dd) else 0.0


def beta_alpha(returns: pd.Series, bench: pd.Series, rf_annual: float = 0.0):
    """CAPM beta and annualized Jensen's alpha from daily returns."""
    df = pd.concat([returns, bench], axis=1, keys=["r", "b"]).dropna()
    if len(df) < 20 or df["b"].var() == 0:
        return np.nan, np.nan
    rf_d = rf_annual / TRADING_DAYS
    beta = df["r"].cov(df["b"]) / df["b"].var()
    alpha_d = (df["r"].mean() - rf_d) - beta * (df["b"].mean() - rf_d)
    return float(beta), float(alpha_d * TRADING_DAYS)


def perf_stats(
    equity: pd.Series,
    bench_returns: pd.Series | None = None,
    trades: list[dict] | None = None,
    rf_annual: float = 0.0,
) -> dict:
    rets = equity.pct_change().dropna()
    n = len(rets)
    if n == 0:
        return {}
    total = float(equity.iloc[-1] / equity.iloc[0] - 1)
    years = n / TRADING_DAYS
    cagr = (1 + total) ** (1 / years) - 1 if years > 0 and total > -1 else np.nan
    vol = float(rets.std(ddof=0) * np.sqrt(TRADING_DAYS))
    rf_d = rf_annual / TRADING_DAYS
    sharpe = float((rets.mean() - rf_d) / rets.std(ddof=0) * np.sqrt(TRADING_DAYS)) if rets.std(ddof=0) > 0 else np.nan
    downside = rets[rets < rf_d]
    sortino = (
        float((rets.mean() - rf_d) / downside.std(ddof=0) * np.sqrt(TRADING_DAYS))
        if len(downside) > 1 and downside.std(ddof=0) > 0
        else np.nan
    )
    stats = {
        "total_return": total,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown(equity),
        "n_days": n,
    }
    if bench_returns is not None:
        b, a = beta_alpha(rets, bench_returns, rf_annual)
        stats["beta"] = b
        stats["alpha"] = a
    if trades is not None:
        pnl = np.array([t["pnl"] for t in trades])
        stats["n_trades"] = len(pnl)
        stats["win_rate"] = float((pnl > 0).mean()) if len(pnl) else np.nan
        wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
        stats["profit_factor"] = float(wins / losses) if losses > 0 else np.inf if wins > 0 else np.nan
        stats["avg_trade_pnl"] = float(pnl.mean()) if len(pnl) else np.nan
    return stats


# --------------------------------------------------- engine 1: rebalance

def run_rebalance(
    close: pd.DataFrame,
    lookback: int = 20,
    top_n: int = 5,
    hold_days: int = 5,
    slippage_bps: float = 5.0,
    capital: float = 100.0,
) -> tuple[pd.Series, pd.DataFrame]:
    """Cross-sectional momentum: every hold_days, hold top_n by lookback ROC."""
    rets = close.pct_change()
    score = close.pct_change(lookback)
    weights = pd.DataFrame(0.0, index=close.index, columns=close.columns)

    start = lookback + 1
    rebalance_idx = range(start, len(close), hold_days)
    current = pd.Series(0.0, index=close.columns)
    j = list(rebalance_idx)
    ptr = 0
    for i in range(start, len(close)):
        if ptr < len(j) and i == j[ptr]:
            row = score.iloc[i].dropna()
            top = row.nlargest(top_n)
            current = pd.Series(0.0, index=close.columns)
            if len(top):
                current[top.index] = 1.0 / len(top)
            ptr += 1
        weights.iloc[i] = current

    turnover = weights.diff().abs().sum(axis=1).fillna(0.0)
    port_ret = (weights.shift(1) * rets).sum(axis=1) - turnover * slippage_bps / 1e4
    port_ret = port_ret.iloc[start:]
    equity = capital * (1 + port_ret).cumprod()
    equity.iloc[0] = capital * (1 + port_ret.iloc[0])
    return equity, weights


# ------------------------------------------------ engine 2: signal trades

@dataclass
class Position:
    ticker: str
    shares: float
    entry_price: float
    entry_i: int
    stop: float


@dataclass
class TradeConfig:
    stop_atr_mult: float = 1.5
    max_hold_days: int = 7
    max_positions: int = 5
    slippage_bps: float = 5.0
    capital: float = 100.0


def run_signal_trades(
    panel: dict[str, pd.DataFrame],
    entries: pd.DataFrame,
    exits: pd.DataFrame | None,
    cfg: TradeConfig | None = None,
) -> tuple[pd.Series, list[dict]]:
    """Event-loop backtest. entries/exits are boolean DataFrames (dates x tickers)."""
    if cfg is None:
        cfg = TradeConfig()
    elif isinstance(cfg, dict):
        cfg = TradeConfig(**cfg)
    close, open_, low = panel["close"], panel["open"], panel["low"]
    atr = ind.atr(panel["high"], panel["low"], close)
    slip = cfg.slippage_bps / 1e4

    cash = cfg.capital
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity = pd.Series(index=close.index, dtype=float)

    for i, date in enumerate(close.index):
        px = close.iloc[i]
        # --- exits
        for t in list(positions):
            pos = positions[t]
            exit_price = None
            reason = None
            lo, op = low.iloc[i].get(t, np.nan), open_.iloc[i].get(t, np.nan)
            if np.isfinite(lo) and lo <= pos.stop:
                exit_price = min(op, pos.stop) if np.isfinite(op) else pos.stop
                reason = "stop"
            elif exits is not None and i < len(exits) and bool(exits.iloc[i].get(t, False)):
                exit_price = px.get(t, np.nan)
                reason = "signal"
            elif i - pos.entry_i >= cfg.max_hold_days:
                exit_price = px.get(t, np.nan)
                reason = "timeout"
            if exit_price is not None and np.isfinite(exit_price):
                proceeds = pos.shares * exit_price * (1 - slip)
                cash += proceeds
                trades.append(
                    {
                        "ticker": t,
                        "entry_date": close.index[pos.entry_i],
                        "exit_date": date,
                        "entry": pos.entry_price,
                        "exit": exit_price,
                        "pnl": proceeds - pos.shares * pos.entry_price * (1 + slip),
                        "return_pct": exit_price / pos.entry_price - 1,
                        "reason": reason,
                        "days": i - pos.entry_i,
                    }
                )
                del positions[t]

        # --- entries at today's close
        mark = cash + sum(p.shares * px.get(p.ticker, p.entry_price) for p in positions.values())
        if i < len(entries):
            todays = entries.iloc[i]
            candidates = [t for t in close.columns if bool(todays.get(t, False)) and t not in positions]
            for t in candidates:
                if len(positions) >= cfg.max_positions:
                    break
                price = px.get(t, np.nan)
                a = atr.iloc[i].get(t, np.nan)
                if not (np.isfinite(price) and np.isfinite(a) and price > 0):
                    continue
                size = mark / cfg.max_positions
                if size > cash:
                    size = cash
                if size <= 0:
                    continue
                fill = price * (1 + slip)
                shares = size / fill
                cash -= shares * fill
                positions[t] = Position(t, shares, price, i, price - cfg.stop_atr_mult * a)

        equity.iloc[i] = cash + sum(
            p.shares * px.get(p.ticker, p.entry_price) for p in positions.values()
        )

    return equity.dropna(), trades


# --------------------------------------------------------- entry builders

def rsi2_entries(panel, entry_below: float = 10.0, exit_above: float = 65.0):
    close = panel["close"]
    r2 = ind.rsi(close, 2)
    uptrend = close > ind.ema(close, 50)
    return (r2 < entry_below) & uptrend, r2 > exit_above


def macd_entries(panel):
    close = panel["close"]
    line, sig, hist = ind.macd(close)
    cross_up = (line > sig) & (line.shift(1) <= sig.shift(1))
    uptrend = close > ind.ema(close, 50)
    return cross_up & uptrend & (hist > 0), (line < sig) & (line.shift(1) >= sig.shift(1))


def bollinger_entries(panel, entry_pctb: float = 0.05, exit_pctb: float = 0.5):
    close = panel["close"]
    pctb = ind.bollinger_percent_b(close)
    uptrend = close > ind.ema(close, 50)
    return (pctb < entry_pctb) & uptrend, pctb > exit_pctb


def buy_hold_equity(close: pd.Series, capital: float = 100.0) -> pd.Series:
    rets = close.pct_change().fillna(0.0)
    return capital * (1 + rets).cumprod()
