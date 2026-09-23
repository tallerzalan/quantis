"""Backtesting engines and performance statistics.

Two engines share the same stats:
  run_rebalance      - vectorized periodic rebalance into top-N ranked names
                       (cross-sectional momentum). Weights decided at close t
                       earn returns from t to t+1 (weights are shifted; no
                       look-ahead).
  run_signal_trades  - daily event loop for entry-signal strategies (RSI-2
                       reversion, MACD cross, Bollinger reversion) with
                       ATR/percent stops, timeouts, and exit signals. Signals
                       observed at close t execute at open t+1. Stops fill at
                       the stop price (or the open on a gap).
Slippage, half the quoted spread, and commission are charged per side.
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
    spread_bps: float = 2.0,
    commission_bps: float = 1.0,
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
    one_way_cost = (slippage_bps + spread_bps / 2 + commission_bps) / 1e4
    port_ret = (weights.shift(1) * rets).sum(axis=1) - turnover * one_way_cost
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
    entry_date: pd.Timestamp
    stop: float
    entry_cost: float
    entry_fees: float
    entry_signal_date: pd.Timestamp


@dataclass
class TradeConfig:
    stop_atr_mult: float = 1.5
    max_hold_days: int = 7
    max_positions: int = 5
    slippage_bps: float = 5.0
    spread_bps: float = 2.0
    commission_bps: float = 1.0
    capital: float = 100.0

    def __post_init__(self):
        if self.stop_atr_mult <= 0 or self.max_hold_days < 1 or self.max_positions < 1:
            raise ValueError("Stop, holding period, and position count must be positive.")
        if min(self.slippage_bps, self.spread_bps, self.commission_bps) < 0:
            raise ValueError("Trading costs cannot be negative.")
        if self.capital <= 0:
            raise ValueError("Capital must be positive.")


def run_signal_trades(
    panel: dict[str, pd.DataFrame],
    entries: pd.DataFrame,
    exits: pd.DataFrame | None,
    cfg: TradeConfig | None = None,
) -> tuple[pd.Series, list[dict]]:
    """Backtest close-generated signals without look-ahead.

    ``entries`` and ``exits`` are boolean DataFrames indexed like the OHLC
    panel. A signal observed at close ``t`` is eligible to execute at open
    ``t+1``. The initial stop uses ATR known at ``t``. Market orders pay
    slippage plus half the quoted spread; commission is charged separately.
    """
    if cfg is None:
        cfg = TradeConfig()
    elif isinstance(cfg, dict):
        cfg = TradeConfig(**cfg)
    close, open_, low = panel["close"], panel["open"], panel["low"]
    atr = ind.atr(panel["high"], panel["low"], close)
    market_cost = (cfg.slippage_bps + cfg.spread_bps / 2) / 1e4
    commission = cfg.commission_bps / 1e4

    cash = cfg.capital
    positions: dict[str, Position] = {}
    trades: list[dict] = []
    equity = pd.Series(index=close.index, dtype=float)

    for i, date in enumerate(close.index):
        px = close.iloc[i]
        opx = open_.iloc[i]

        # --- orders known before today's open, plus overnight stop gaps
        for t in list(positions):
            pos = positions[t]
            raw_exit = None
            reason = None
            op = open_.iloc[i].get(t, np.nan)
            signal_exit = (
                exits is not None and i > 0 and i - 1 < len(exits)
                and bool(exits.iloc[i - 1].get(t, False))
            )
            timed_out = i - pos.entry_i >= cfg.max_hold_days
            if np.isfinite(op) and op <= pos.stop:
                raw_exit = op
                reason = "stop"
            elif signal_exit and np.isfinite(op):
                raw_exit = op
                reason = "signal"
            elif timed_out and np.isfinite(op):
                raw_exit = op
                reason = "timeout"

            if raw_exit is not None:
                cash = _close_position(
                    positions, trades, t, raw_exit, date, i, cash,
                    market_cost, commission, reason,
                )

        # --- entries from yesterday's close signal execute at today's open
        # Size at information available at the open; today's close is still unknown.
        mark = cash + sum(
            p.shares * opx.get(p.ticker, p.entry_price) for p in positions.values()
        )
        if i > 0 and i - 1 < len(entries):
            prior_signals = entries.iloc[i - 1]
            candidates = [
                t for t in close.columns
                if bool(prior_signals.get(t, False)) and t not in positions
            ]
            for t in candidates:
                if len(positions) >= cfg.max_positions:
                    break
                price = opx.get(t, np.nan)
                a = atr.iloc[i - 1].get(t, np.nan)
                if not (np.isfinite(price) and np.isfinite(a) and price > 0):
                    continue
                size = mark / cfg.max_positions
                if size > cash:
                    size = cash
                if size <= 0:
                    continue
                fill = price * (1 + market_cost)
                shares = size / (fill * (1 + commission))
                entry_cost = shares * fill * (1 + commission)
                entry_fees = entry_cost - shares * price
                cash -= entry_cost
                positions[t] = Position(
                    t, shares, fill, i, date, price - cfg.stop_atr_mult * a,
                    entry_cost, entry_fees, close.index[i - 1],
                )

        # --- intraday stops, including positions opened this morning
        for t in list(positions):
            pos = positions[t]
            lo = low.iloc[i].get(t, np.nan)
            if np.isfinite(lo) and lo <= pos.stop:
                cash = _close_position(
                    positions, trades, t, pos.stop, date, i, cash,
                    market_cost, commission, "stop",
                )

        equity.iloc[i] = cash + sum(
            p.shares * px.get(p.ticker, p.entry_price) for p in positions.values()
        )

    return equity.dropna(), trades


def _close_position(
    positions: dict[str, Position],
    trades: list[dict],
    ticker: str,
    raw_exit: float,
    exit_date,
    exit_i: int,
    cash: float,
    market_cost: float,
    commission: float,
    reason: str,
) -> float:
    """Close one long position and append a net-of-cost trade record."""
    pos = positions[ticker]
    fill = raw_exit * (1 - market_cost)
    gross_proceeds = pos.shares * fill
    exit_commission = gross_proceeds * commission
    net_proceeds = gross_proceeds - exit_commission
    pnl = net_proceeds - pos.entry_cost
    trades.append(
        {
            "ticker": ticker,
            "signal_date": pos.entry_signal_date,
            "entry_date": pos.entry_date,
            "exit_date": exit_date,
            "entry": pos.entry_price,
            "exit": fill,
            "pnl": pnl,
            "return_pct": pnl / pos.entry_cost,
            "costs": pos.entry_fees + (pos.shares * raw_exit - net_proceeds),
            "reason": reason,
            "days": exit_i - pos.entry_i,
        }
    )
    del positions[ticker]
    return cash + net_proceeds


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
