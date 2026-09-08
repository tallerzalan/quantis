"""Statistically significant price-move detection and catalyst attribution.

A move is significant when the day's return is large relative to the EWMA
volatility of returns *up to the previous day* (so a spike never dampens its
own significance). Attribution matches each event against earnings dates,
split/dividend ex-dates, recent headlines, and same-day market co-movement.
All functions are pure; network fetching lives in data.py.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

Z_THRESHOLD = 2.5
VOL_SPAN = 21
MIN_HISTORY = 20
MIN_ABS_RET = 0.01   # a "significant" day must also move at least 1%
SIGMA_FLOOR = 1e-6   # below this, returns are effectively constant: no z-score


def two_sided_pvalue(z: float) -> float:
    """P(|N(0,1)| >= |z|)."""
    return math.erfc(abs(z) / math.sqrt(2.0))


def move_significance(
    close: pd.Series,
    volume: pd.Series | None = None,
    z_thresh: float = Z_THRESHOLD,
    span: int = VOL_SPAN,
) -> pd.DataFrame:
    """Days whose return is a >= z_thresh sigma outlier vs prior volatility.

    Returns a DataFrame indexed by date with columns [ret, z, pvalue, rvol],
    ordered oldest first.
    """
    close = close.dropna()
    rets = close.pct_change()
    sigma = rets.ewm(span=span, min_periods=MIN_HISTORY).std().shift(1)
    z = rets / sigma.where(sigma > SIGMA_FLOOR)
    out = pd.DataFrame({"ret": rets, "z": z})
    if volume is not None:
        rvol = volume.reindex(close.index) / volume.reindex(close.index).rolling(20).mean().shift(1)
        out["rvol"] = rvol
    else:
        out["rvol"] = np.nan
    out = out[(out["z"].abs() >= z_thresh) & (out["ret"].abs() >= MIN_ABS_RET)].copy()
    out["pvalue"] = [two_sided_pvalue(v) for v in out["z"]]
    return out


def market_zscores(bench_close: pd.Series, span: int = VOL_SPAN) -> pd.Series:
    """Same z-score construction, applied to the benchmark."""
    rets = bench_close.dropna().pct_change()
    sigma = rets.ewm(span=span, min_periods=MIN_HISTORY).std().shift(1)
    return rets / sigma.where(sigma > SIGMA_FLOOR)


def _trading_gap(index: pd.DatetimeIndex, earlier: pd.Timestamp, later: pd.Timestamp) -> int | None:
    """Trading sessions from `earlier` to `later` along `index` (None if reversed)."""
    if later < earlier:
        return None
    return int(index.searchsorted(later) - index.searchsorted(earlier))


def attribute_events(
    events: pd.DataFrame,
    index: pd.DatetimeIndex,
    earnings: list[pd.Timestamp] | None = None,
    actions: pd.DataFrame | None = None,
    news: list[dict] | None = None,
    bench_close: pd.Series | None = None,
) -> list[dict]:
    """Attach the most plausible catalyst to each significant move.

    news items are dicts with keys [when (Timestamp), title, publisher, url].
    actions is a DataFrame indexed by ex-date with columns like
    ["Dividends", "Stock Splits"]. Priority: earnings > split > dividend >
    news > market-wide co-move > unknown.
    """
    earnings = sorted(earnings or [])
    news = news or []
    bench_z = market_zscores(bench_close) if bench_close is not None else pd.Series(dtype=float)
    bench_ret = bench_close.pct_change() if bench_close is not None else pd.Series(dtype=float)

    out = []
    for date, row in events.iterrows():
        ev: dict = {
            "date": date,
            "ret": float(row["ret"]),
            "z": float(row["z"]),
            "pvalue": float(row["pvalue"]),
            "rvol": float(row["rvol"]) if np.isfinite(row.get("rvol", np.nan)) else None,
            "direction": "up" if row["ret"] > 0 else "down",
        }

        bz = bench_z.get(date, np.nan)
        same_sign = np.isfinite(bz) and np.sign(bz) == np.sign(row["z"])
        ev["market_move"] = bool(same_sign and abs(bz) >= 1.5)
        ev["bench_ret"] = float(bench_ret.get(date)) if np.isfinite(bench_ret.get(date, np.nan)) else None

        # earnings released on the event day (pre-market) or the prior
        # session (after the close) both print on this bar
        ev["catalyst"] = "unknown"
        for e in earnings:
            gap = _trading_gap(index, pd.Timestamp(e).normalize(), date)
            if gap is not None and gap <= 1:
                ev["catalyst"] = "earnings"
                ev["earnings_date"] = pd.Timestamp(e).normalize()
                break

        if ev["catalyst"] == "unknown" and actions is not None and not actions.empty:
            acts = actions.loc[actions.index.normalize() == date.normalize()]
            if not acts.empty:
                if (acts.get("Stock Splits", pd.Series(dtype=float)) != 0).any():
                    ev["catalyst"] = "split"
                elif (acts.get("Dividends", pd.Series(dtype=float)) != 0).any():
                    ev["catalyst"] = "dividend"

        matched = [
            n for n in news
            if abs((pd.Timestamp(n["when"]).normalize() - date.normalize()).days) <= 1
        ]
        ev["headlines"] = matched[:3]
        if ev["catalyst"] == "unknown" and matched:
            ev["catalyst"] = "news"
        if ev["catalyst"] == "unknown" and ev["market_move"]:
            ev["catalyst"] = "market"
        out.append(ev)
    return out
