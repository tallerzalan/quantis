"""Markowitz mean-variance portfolio optimization.

Expected returns: exponentially weighted mean of daily returns (recent data
counts more - appropriate for a short horizon), annualized.
Covariance: Ledoit-Wolf shrinkage (stable when the window is short relative
to the number of assets), annualized.
Solver: scipy SLSQP; long-only, fully invested, per-name weight cap.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

TRADING_DAYS = 252


def expected_returns(returns: pd.DataFrame, halflife: int = 63) -> pd.Series:
    """Annualized EW mean of daily returns."""
    return returns.ewm(halflife=halflife).mean().iloc[-1] * TRADING_DAYS


def shrunk_covariance(returns: pd.DataFrame) -> pd.DataFrame:
    clean = returns.dropna()
    lw = LedoitWolf().fit(clean.values)
    return pd.DataFrame(lw.covariance_ * TRADING_DAYS, index=returns.columns, columns=returns.columns)


def _solve(objective, n: int, cap: float, extra_constraints=()):
    w0 = np.full(n, 1.0 / n)
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1.0}, *extra_constraints]
    res = minimize(
        objective,
        w0,
        method="SLSQP",
        bounds=[(0.0, cap)] * n,
        constraints=cons,
        options={"maxiter": 500, "ftol": 1e-10},
    )
    return res.x if res.success else w0


def min_variance(cov: pd.DataFrame, cap: float = 0.4) -> pd.Series:
    S = cov.values
    w = _solve(lambda w: w @ S @ w, len(cov), cap)
    return pd.Series(w, index=cov.index).clip(lower=0)


def max_sharpe(mu: pd.Series, cov: pd.DataFrame, cap: float = 0.4, rf: float = 0.0) -> tuple[pd.Series, bool]:
    """Returns (weights, fell_back). Falls back to min-variance when no asset
    beats the risk-free rate (Sharpe maximization is then ill-posed)."""
    if (mu <= rf).all():
        return min_variance(cov, cap), True
    m, S = mu.values, cov.values

    def neg_sharpe(w):
        vol = np.sqrt(max(w @ S @ w, 1e-12))
        return -(w @ m - rf) / vol

    w = _solve(neg_sharpe, len(mu), cap)
    return pd.Series(w, index=mu.index).clip(lower=0), False


def portfolio_stats(w: pd.Series, mu: pd.Series, cov: pd.DataFrame, rf: float = 0.0) -> dict:
    ret = float(w @ mu)
    vol = float(np.sqrt(w @ cov.values @ w))
    return {"return": ret, "volatility": vol, "sharpe": (ret - rf) / vol if vol > 0 else np.nan}


def max_return_under_cap(mu: pd.Series, cap: float) -> float:
    """Highest expected return reachable with long-only capped weights."""
    w = pd.Series(0.0, index=mu.index)
    remaining = 1.0
    for t in mu.sort_values(ascending=False).index:
        take = min(cap, remaining)
        w[t] = take
        remaining -= take
        if remaining <= 1e-12:
            break
    return float(w @ mu)


def efficient_frontier(mu: pd.Series, cov: pd.DataFrame, cap: float = 0.4, n_points: int = 25) -> pd.DataFrame:
    """Min-vol portfolio at each target return between min-var return and the
    highest return actually reachable under the weight cap (targets beyond that
    are infeasible and would pollute the frontier with fallback points)."""
    base = min_variance(cov, cap)
    lo = float(base @ mu)
    hi = max_return_under_cap(mu, cap)
    if hi <= lo:
        hi = lo + abs(lo) * 0.5 + 1e-3
    rows = []
    S = cov.values
    m = mu.values
    for target in np.linspace(lo, hi, n_points):
        w = _solve(
            lambda w: w @ S @ w,
            len(mu),
            cap,
            extra_constraints=[{"type": "eq", "fun": lambda w, t=target: w @ m - t}],
        )
        rows.append({"return": float(w @ m), "volatility": float(np.sqrt(w @ S @ w))})
    return pd.DataFrame(rows)


def implied_returns(cov: pd.DataFrame, market_weights: pd.Series, delta: float = 2.5) -> pd.Series:
    """Reverse-optimization: the excess returns the market's own weights imply,
    given the covariance and a risk-aversion delta. This is Black-Litterman's
    equilibrium prior - what you'd believe before adding any opinion."""
    w = market_weights.reindex(cov.index).fillna(0.0)
    return pd.Series(delta * cov.values @ w.values, index=cov.index)


def black_litterman(
    cov: pd.DataFrame,
    market_weights: pd.Series,
    views: pd.Series,
    delta: float = 2.5,
    tau: float = 0.05,
    view_confidence: float = 1.0,
) -> pd.Series:
    """Black-Litterman posterior expected returns.

    Blends the market-equilibrium prior (from `implied_returns`) with absolute
    views on each asset (here P = identity, Q = `views`). `view_confidence`
    scales how strongly the views pull away from equilibrium (higher = more).
    Returns annualized expected returns aligned to `cov`.
    """
    assets = list(cov.index)
    sigma = cov.values
    pi = implied_returns(cov, market_weights, delta).values
    q = views.reindex(assets).fillna(pd.Series(pi, index=assets)).values

    tau_sigma = tau * sigma
    # Ω: view uncertainty; smaller when we're more confident in the views.
    omega = np.diag(np.diag(tau_sigma)) / max(view_confidence, 1e-6)

    inv_tau_sigma = np.linalg.pinv(tau_sigma)
    inv_omega = np.linalg.pinv(omega)
    posterior_cov = np.linalg.pinv(inv_tau_sigma + inv_omega)
    mu = posterior_cov @ (inv_tau_sigma @ pi + inv_omega @ q)
    return pd.Series(mu, index=assets)


def dollar_allocation(w: pd.Series, capital: float = 100.0, min_dollars: float = 1.0) -> pd.Series:
    """Weights -> dollars, dropping dust positions and re-scaling to capital."""
    d = (w * capital).round(2)
    d = d[d >= min_dollars]
    if d.empty:
        return d
    return (d / d.sum() * capital).round(2).sort_values(ascending=False)
