"""Monte Carlo price simulation by circular block bootstrap of real returns.

Resampling actual daily returns (in blocks, to keep short-run streaks)
preserves the fat tails and skew a normal/GBM simulation would erase.
Paths are arrays of cumulative growth factors, shape (n_paths, horizon+1),
column 0 always 1.0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_PATHS = 2000
DEFAULT_HORIZON = 21
DEFAULT_BLOCK = 5
VOL_SPAN = 21


def ewma_sigma(returns: pd.Series, span: int = VOL_SPAN) -> pd.Series:
    """Per-day EWMA volatility of daily returns."""
    return pd.Series(returns).ewm(span=span, min_periods=10).std()


def sample_stats(returns: pd.Series, span: int = VOL_SPAN) -> dict:
    """The distribution facts behind a simulation: current vs full-sample
    volatility (annualized), drift, skew, excess kurtosis."""
    r = pd.Series(returns).dropna()
    ann = float(np.sqrt(252))
    cur = float(ewma_sigma(r, span).iloc[-1])
    hist = float(r.std())
    return {
        "n_days": int(len(r)),
        "ann_vol_current": cur * ann,
        "ann_vol_history": hist * ann,
        "vol_ratio": cur / hist if hist > 0 else None,
        "drift_ann": float(r.mean() * 252),
        "skew": float(r.skew()),
        "kurtosis": float(r.kurt()),
    }


def simulate_paths(
    returns: pd.Series,
    horizon: int = DEFAULT_HORIZON,
    n_paths: int = DEFAULT_PATHS,
    block: int = DEFAULT_BLOCK,
    seed: int | None = None,
    vol_mode: str = "history",
    span: int = VOL_SPAN,
) -> np.ndarray:
    """vol_mode 'history' resamples raw returns (unconditional distribution).
    vol_mode 'current' resamples returns standardized by their own EWMA
    volatility, re-scaled to TODAY's volatility (a filtered bootstrap) — more
    accurate over short horizons when the stock is calmer or wilder than its
    yearly average."""
    r = pd.Series(returns).dropna()
    if len(r) < 30:
        raise ValueError("Need at least 30 daily returns to simulate.")
    if vol_mode == "current":
        sigma = ewma_sigma(r, span)
        ok = sigma.notna() & (sigma > 1e-8)
        pool = (r[ok] / sigma[ok]).values * float(sigma.iloc[-1])
    else:
        pool = r.values
    rng = np.random.default_rng(seed)
    block = max(1, min(block, len(pool)))
    n_blocks = int(np.ceil(horizon / block))
    starts = rng.integers(0, len(pool), size=(n_paths, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % len(pool)
    draws = pool[idx].reshape(n_paths, n_blocks * block)[:, :horizon]
    growth = np.cumprod(1.0 + draws, axis=1)
    return np.concatenate([np.ones((n_paths, 1)), growth], axis=1)


def fan_bands(paths: np.ndarray, last_price: float) -> pd.DataFrame:
    """Per-day price percentiles: columns p05, p25, p50, p75, p95."""
    qs = np.percentile(paths, [5, 25, 50, 75, 95], axis=0) * last_price
    return pd.DataFrame(qs.T, columns=["p05", "p25", "p50", "p75", "p95"])


def summarize(paths: np.ndarray) -> dict:
    end = paths[:, -1] - 1.0
    return {
        "prob_up": float((end > 0).mean()),
        "exp_return": float(end.mean()),
        "p05": float(np.percentile(end, 5)),
        "p50": float(np.percentile(end, 50)),
        "p95": float(np.percentile(end, 95)),
    }


def dip_probabilities(paths: np.ndarray, dips: list[float]) -> dict[float, float]:
    """Chance the path's low (after day 0) reaches each dip depth."""
    lows = paths[:, 1:].min(axis=1)
    return {float(d): float((lows <= 1.0 - d).mean()) for d in dips}


def best_entry(paths: np.ndarray) -> dict:
    """When and how low the simulated paths bottom out."""
    future = paths[:, 1:]
    low_day = future.argmin(axis=1) + 1  # 1-based session number
    low_val = future.min(axis=1)
    days = np.arange(1, future.shape[1] + 1)
    hist = [int((low_day == d).sum()) for d in days]
    return {
        "median_low": float(np.median(low_val)),
        "p25_low": float(np.percentile(low_val, 25)),
        "median_day": int(np.median(low_day)),
        "p75_day": int(np.percentile(low_day, 75)),
        "day_hist": hist,
    }


def equity_confidence(
    strategy_returns: pd.Series,
    capital: float = 100.0,
    n_paths: int = 1000,
    block: int = DEFAULT_BLOCK,
    seed: int | None = None,
    bench_total: float | None = None,
) -> dict:
    """Bootstrap a strategy's realized daily returns into alternate histories.

    Answers: was the backtest result skill or one lucky ordering of days?
    Returns final-value percentiles, chance of loss, drawdown range, and
    (if bench_total given) the chance of beating buy-and-hold."""
    r = pd.Series(strategy_returns).dropna()
    paths = simulate_paths(r, horizon=len(r), n_paths=n_paths, block=block, seed=seed)
    end = paths[:, -1]
    runmax = np.maximum.accumulate(paths, axis=1)
    dd = (paths / runmax - 1.0).min(axis=1)
    out = {
        "n_paths": n_paths,
        "final": {f"p{q:02d}": float(np.percentile(end, q)) * capital for q in (5, 25, 50, 75, 95)},
        "prob_loss": float((end < 1.0).mean()),
        "dd_median": float(np.median(dd)),
        "dd_worst5": float(np.percentile(dd, 5)),
    }
    if bench_total is not None and np.isfinite(bench_total):
        out["prob_beat_bench"] = float((end - 1.0 > bench_total).mean())
    return out


def _exit_return(path: np.ndarray, entry_i: int, entry_px: float, target: float, stop: float) -> tuple[float, int]:
    """First target/stop crossing after entry, else timeout at path end."""
    for j in range(entry_i + 1, len(path)):
        r = path[j] / entry_px - 1.0
        if r >= target:
            return target, j
        if r <= -stop:
            return -stop, j
    return path[-1] / entry_px - 1.0, len(path) - 1


def dip_buy_outcomes(
    paths: np.ndarray,
    dip: float,
    target: float,
    stop: float,
) -> dict:
    """Test 'wait for a -dip limit fill, then sell at +target / -stop /
    timeout' on every path, against buying at day 0 with the same exits."""
    filled_rets, wait_days, now_rets = [], [], []
    for path in paths:
        now_rets.append(_exit_return(path, 0, 1.0, target, stop)[0])
        hit = np.nonzero(path[1:] <= 1.0 - dip)[0]
        if len(hit) == 0:
            continue  # never filled: stayed in cash, 0 return
        i = int(hit[0]) + 1
        wait_days.append(i)
        filled_rets.append(_exit_return(path, i, 1.0 - dip, target, stop)[0])

    filled = np.array(filled_rets)
    now = np.array(now_rets)
    return {
        "fill_rate": len(filled) / len(paths),
        "win_rate": float((filled > 0).mean()) if len(filled) else None,
        "avg_ret_filled": float(filled.mean()) if len(filled) else None,
        "avg_ret_overall": float(filled.sum() / len(paths)),
        "median_days_to_fill": float(np.median(wait_days)) if wait_days else None,
        "buy_now": {
            "win_rate": float((now > 0).mean()),
            "avg_ret": float(now.mean()),
        },
    }
