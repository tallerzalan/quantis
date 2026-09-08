"""Composite Quantis Score and trade-idea construction.

The Quantis Score blends four cross-sectional components:
  momentum   - z-scores of 5/10/20-day rate of change
  trend      - EMA stack + MACD histogram, strength-weighted by ADX
  mean-rev   - oversold (low RSI-2 / %B) credited ONLY in uptrends (buy dips)
  volume     - relative volume confirmation
Weights: 0.35 / 0.25 / 0.25 / 0.15. Scores are ranked to a 0-100 percentile.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind

WEIGHTS = {"momentum": 0.35, "trend": 0.25, "meanrev": 0.25, "volume": 0.15}


def _z(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - s.mean()) / sd).clip(-3, 3)


def compute_features(panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Latest-bar feature row per ticker (index = ticker)."""
    close, high, low, volume = panel["close"], panel["high"], panel["low"], panel["volume"]
    ema20, ema50 = ind.ema(close, 20), ind.ema(close, 50)
    _, _, hist = ind.macd(close)
    feats = pd.DataFrame(
        {
            "last": close.iloc[-1],
            "roc1": ind.roc(close, 1).iloc[-1],
            "roc5": ind.roc(close, 5).iloc[-1],
            "roc10": ind.roc(close, 10).iloc[-1],
            "roc20": ind.roc(close, 20).iloc[-1],
            "rsi2": ind.rsi(close, 2).iloc[-1],
            "rsi14": ind.rsi(close, 14).iloc[-1],
            "pctb": ind.bollinger_percent_b(close).iloc[-1],
            "macd_hist": hist.iloc[-1],
            "ema20": ema20.iloc[-1],
            "ema50": ema50.iloc[-1],
            "adx": ind.adx(high, low, close).iloc[-1],
            "atr": ind.atr(high, low, close).iloc[-1],
            "rvol": ind.relative_volume(volume).iloc[-1],
        }
    )
    return feats.dropna(subset=["last", "roc20", "atr"])


def edge_scores(feats: pd.DataFrame) -> pd.DataFrame:
    """Adds component scores, raw edge, and 0-100 percentile Quantis Score."""
    f = feats.copy()
    f["momentum"] = (_z(f["roc5"]) + _z(f["roc10"]) + _z(f["roc20"])) / 3

    stack = (
        (f["last"] > f["ema20"]).astype(float)
        + (f["ema20"] > f["ema50"]).astype(float)
        + (f["macd_hist"] > 0).astype(float)
    )
    f["trend"] = _z(stack * (1 + f["adx"].fillna(0) / 100))

    uptrend = f["last"] > f["ema50"]
    dip = ((50 - f["rsi2"]) / 50 + (0.5 - f["pctb"])) / 2
    f["meanrev"] = _z(dip.where(uptrend, 0.0))

    f["volume_score"] = _z(f["rvol"].fillna(1.0)).clip(-2, 2)

    f["edge_raw"] = (
        WEIGHTS["momentum"] * f["momentum"]
        + WEIGHTS["trend"] * f["trend"]
        + WEIGHTS["meanrev"] * f["meanrev"]
        + WEIGHTS["volume"] * f["volume_score"]
    )
    f["edge"] = f["edge_raw"].rank(pct=True) * 100
    return f.sort_values("edge", ascending=False)


def cap_weights(w: pd.Series, cap: float) -> pd.Series:
    """Renormalize weights to sum 1 with a per-name cap (iterative water-filling)."""
    w = w.clip(lower=0.0)
    if w.sum() == 0:
        return pd.Series(1.0 / len(w), index=w.index)
    w = w / w.sum()
    for _ in range(50):
        over = w > cap
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        under = ~over & (w > 0)
        if not under.any() or w[under].sum() == 0:
            break
        w[under] += excess * w[under] / w[under].sum()
    return w / w.sum()


def trade_ideas(
    scored: pd.DataFrame,
    capital: float = 100.0,
    n: int = 5,
    stop_atr_mult: float = 1.5,
    reward_risk: float = 2.0,
    max_weight: float = 0.25,
) -> pd.DataFrame:
    """Top-n ideas with entry/stop/target, hold horizon, and dollar sizing."""
    top = scored.head(n).copy()
    risk = stop_atr_mult * top["atr"]
    top["entry"] = top["last"]
    top["stop"] = top["entry"] - risk
    top["target"] = top["entry"] + reward_risk * risk
    top["risk_pct"] = 100 * risk / top["entry"]
    top["hold_days"] = np.where(top["momentum"] >= top["meanrev"], "5-7", "2-4")

    base = (top["edge_raw"] - top["edge_raw"].min()) + 0.25 * top["edge_raw"].std(ddof=0) + 1e-9
    top["weight"] = cap_weights(base, max_weight)
    top["dollars"] = (top["weight"] * capital).round(2)
    return top
