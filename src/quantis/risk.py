"""Risk metrics: CAPM beta / Jensen's alpha, Sharpe, Sortino, VaR, drawdown."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import TRADING_DAYS, beta_alpha, max_drawdown


def annualized_vol(returns: pd.Series) -> float:
    return float(returns.std(ddof=0) * np.sqrt(TRADING_DAYS))


def sharpe_ratio(returns: pd.Series, rf_annual: float = 0.0) -> float:
    sd = returns.std(ddof=0)
    if sd == 0 or not np.isfinite(sd):
        return np.nan
    return float((returns.mean() - rf_annual / TRADING_DAYS) / sd * np.sqrt(TRADING_DAYS))


def sortino_ratio(returns: pd.Series, rf_annual: float = 0.0) -> float:
    rf_d = rf_annual / TRADING_DAYS
    downside = returns[returns < rf_d]
    sd = downside.std(ddof=0)
    if len(downside) < 2 or sd == 0 or not np.isfinite(sd):
        return np.nan
    return float((returns.mean() - rf_d) / sd * np.sqrt(TRADING_DAYS))


def hist_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """1-day historical VaR, reported as a positive loss fraction."""
    if len(returns) < 30:
        return np.nan
    return float(-np.nanpercentile(returns, 100 * (1 - confidence)))


def cvar(returns: pd.Series, confidence: float = 0.95) -> float:
    """Expected shortfall: average loss on the worst (1-confidence) tail of days,
    as a positive loss fraction. Answers 'when it's bad, how bad on average?'."""
    r = returns.dropna()
    if len(r) < 30:
        return np.nan
    cutoff = np.nanpercentile(r, 100 * (1 - confidence))
    tail = r[r <= cutoff]
    return float(-tail.mean()) if len(tail) else np.nan


def cornish_fisher_var(returns: pd.Series, confidence: float = 0.95) -> float:
    """VaR adjusted for skew and fat tails (Cornish-Fisher expansion). Closer to
    reality than the normal assumption for stocks, which crash more than a bell
    curve allows. Positive loss fraction."""
    r = returns.dropna()
    if len(r) < 30:
        return np.nan
    mu, sd = r.mean(), r.std(ddof=0)
    if sd == 0 or not np.isfinite(sd):
        return np.nan
    from scipy.stats import kurtosis, norm, skew
    s = float(skew(r))
    k = float(kurtosis(r))  # excess kurtosis
    z = norm.ppf(1 - confidence)
    zcf = (z + (z**2 - 1) * s / 6 + (z**3 - 3 * z) * k / 24
           - (2 * z**3 - 5 * z) * s**2 / 36)
    return float(-(mu + zcf * sd))


def downside_beta(returns: pd.Series, bench: pd.Series) -> float:
    """Beta measured only on days the market fell - how much a name amplifies
    losses, which matters more than average beta for capital preservation."""
    df = pd.concat([returns, bench], axis=1, keys=["r", "b"]).dropna()
    down = df[df["b"] < 0]
    if len(down) < 20:
        return np.nan
    var_b = down["b"].var(ddof=0)
    if var_b == 0 or not np.isfinite(var_b):
        return np.nan
    return float(down["r"].cov(down["b"]) / var_b)


def rolling_beta(returns: pd.Series, bench: pd.Series, window: int = 63) -> pd.Series:
    """Time series of beta over a trailing window (default ~one quarter)."""
    df = pd.concat([returns, bench], axis=1, keys=["r", "b"]).dropna()
    cov = df["r"].rolling(window).cov(df["b"])
    var = df["b"].rolling(window).var(ddof=0)
    return (cov / var).dropna()


def calmar_ratio(returns: pd.Series) -> float:
    """Annualized return divided by max drawdown - reward per unit of worst pain."""
    r = returns.dropna()
    if len(r) < 60:
        return np.nan
    ann = (1 + r).prod() ** (TRADING_DAYS / len(r)) - 1
    dd = abs(max_drawdown((1 + r).cumprod()))
    if dd == 0 or not np.isfinite(dd):
        return np.nan
    return float(ann / dd)


def omega_ratio(returns: pd.Series, threshold: float = 0.0) -> float:
    """Probability-weighted gains over losses relative to a threshold return."""
    r = returns.dropna() - threshold / TRADING_DAYS
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0 or not np.isfinite(losses):
        return np.nan
    return float(gains / losses)


def summary_table(
    returns: pd.DataFrame, bench: pd.Series, rf_annual: float = 0.0
) -> pd.DataFrame:
    """Per-ticker risk summary. `returns` is dates x tickers of daily returns."""
    rows = {}
    for t in returns.columns:
        r = returns[t].dropna()
        if len(r) < 60:
            continue
        beta, alpha = beta_alpha(r, bench, rf_annual)
        equity = (1 + r).cumprod()
        ann_return = float((1 + r).prod() ** (TRADING_DAYS / len(r)) - 1)
        rows[t] = {
            "ann_return": ann_return,
            "beta": beta,
            "down_beta": downside_beta(r, bench),
            "alpha": alpha,
            "sharpe": sharpe_ratio(r, rf_annual),
            "sortino": sortino_ratio(r, rf_annual),
            "calmar": calmar_ratio(r),
            "volatility": annualized_vol(r),
            "var_95": hist_var(r),
            "cvar_95": cvar(r),
            "max_drawdown": max_drawdown(equity),
        }
    return pd.DataFrame(rows).T.sort_values("sharpe", ascending=False)


def portfolio_risk(
    weights: pd.Series, returns: pd.DataFrame, bench: pd.Series, rf_annual: float = 0.0
) -> dict:
    """Risk profile of a weighted portfolio of the given assets."""
    cols = [c for c in weights.index if c in returns.columns]
    if not cols:
        return {}
    w = weights[cols] / weights[cols].sum()
    port = (returns[cols] * w).sum(axis=1).dropna()
    beta, alpha = beta_alpha(port, bench, rf_annual)
    return {
        "beta": beta,
        "down_beta": downside_beta(port, bench),
        "alpha": alpha,
        "sharpe": sharpe_ratio(port, rf_annual),
        "sortino": sortino_ratio(port, rf_annual),
        "calmar": calmar_ratio(port),
        "omega": omega_ratio(port),
        "volatility": annualized_vol(port),
        "var_95": hist_var(port),
        "cvar_95": cvar(port),
        "cf_var_95": cornish_fisher_var(port),
        "max_drawdown": max_drawdown((1 + port).cumprod()),
        "daily_returns": port,
    }
