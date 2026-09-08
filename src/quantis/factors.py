"""Factor-model exposures and sector allocation.

Factor return series are built from liquid ETF proxies (a practical stand-in for
academic long/short factors that needs no special data): the market plus four
style tilts expressed as long-minus-short ETF spreads. Each asset's daily
returns are regressed on those factors (OLS) to recover its factor betas, the
annualized intercept (selection alpha), and R^2 (how much of its movement the
factors explain).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252

# name -> (long ETF, short ETF or None for an outright series)
FACTOR_PROXIES: dict[str, tuple[str, str | None]] = {
    "market": ("SPY", None),    # broad market
    "size": ("IWM", "SPY"),     # small minus large
    "value": ("VTV", "VUG"),    # value minus growth
    "momentum": ("MTUM", "SPY"),  # momentum tilt vs market
    "quality": ("QUAL", "SPY"),   # quality tilt vs market
    "lowvol": ("USMV", "SPY"),    # low-volatility tilt vs market
}

# Every ETF the proxies depend on (for the data layer to fetch).
FACTOR_TICKERS: list[str] = sorted({t for pair in FACTOR_PROXIES.values() for t in pair if t})

FACTOR_LABELS = {
    "market": "Market", "size": "Size", "value": "Value",
    "momentum": "Momentum", "quality": "Quality", "lowvol": "Low volatility",
}


def factor_returns(close: pd.DataFrame) -> pd.DataFrame:
    """Daily factor return series from proxy-ETF closing prices."""
    rets = close.pct_change()
    out: dict[str, pd.Series] = {}
    for name, (long, short) in FACTOR_PROXIES.items():
        if long not in rets.columns:
            continue
        series = rets[long].copy()
        if short and short in rets.columns:
            series = series - rets[short]
        out[name] = series
    return pd.DataFrame(out).dropna()


def factor_exposures(asset_returns: pd.Series, facs: pd.DataFrame) -> dict:
    """OLS of one asset's returns on the factors -> betas, annualized alpha, R^2."""
    df = pd.concat([asset_returns.rename("y"), facs], axis=1).dropna()
    if len(df) < 60:
        return {}
    names = list(facs.columns)
    y = df["y"].to_numpy()
    x = df[names].to_numpy()
    xd = np.column_stack([np.ones(len(x)), x])
    coef, *_ = np.linalg.lstsq(xd, y, rcond=None)
    pred = xd @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {
        "alpha": float(coef[0] * TRADING_DAYS),
        "betas": {n: float(b) for n, b in zip(names, coef[1:])},
        "r2": float(r2),
    }


def exposure_table(returns: pd.DataFrame, facs: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker factor betas + alpha + R^2. `returns` is dates x tickers."""
    rows = {}
    for t in returns.columns:
        e = factor_exposures(returns[t].dropna(), facs)
        if not e:
            continue
        rows[t] = {**e["betas"], "alpha": e["alpha"], "r2": e["r2"]}
    return pd.DataFrame(rows).T


def portfolio_exposures(weights: pd.Series, returns: pd.DataFrame, facs: pd.DataFrame) -> dict:
    """Factor exposures of a weighted portfolio (regress the blended return)."""
    cols = [c for c in weights.index if c in returns.columns]
    if not cols:
        return {}
    w = weights[cols] / weights[cols].sum()
    port = (returns[cols] * w).sum(axis=1)
    return factor_exposures(port, facs)


def sector_allocation(weights: dict[str, float], sectors: dict[str, str]) -> list[dict]:
    """Aggregate portfolio weights by sector, largest first (fractions summing ~1)."""
    total = sum(v for v in weights.values() if v and v > 0) or 1.0
    agg: dict[str, float] = {}
    for t, w in weights.items():
        if not w or w <= 0:
            continue
        sec = sectors.get(t) or "Unknown"
        agg[sec] = agg.get(sec, 0.0) + w / total
    return [{"sector": s, "weight": round(w, 4)} for s, w in sorted(agg.items(), key=lambda kv: -kv[1])]


def concentration(weights: dict[str, float]) -> float:
    """Herfindahl-Hirschman index of the weights (0 = diffuse, 1 = one holding)."""
    vals = np.array([v for v in weights.values() if v and v > 0], dtype=float)
    if vals.size == 0:
        return np.nan
    vals = vals / vals.sum()
    return float((vals ** 2).sum())
