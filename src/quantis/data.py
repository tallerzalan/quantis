"""Market data layer: yfinance downloads normalized into tidy OHLCV panels.

A "panel" is a dict of DataFrames keyed by field ("open", "high", "low",
"close", "volume"), each indexed by date with one column per ticker.
Tickers whose download failed are dropped, never raised.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

FIELDS = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"}

Panel = dict[str, pd.DataFrame]


def download_history(tickers: list[str], period: str = "1y", interval: str = "1d") -> Panel:
    """Bulk-download OHLCV history and return field-keyed panels."""
    raw = yf.download(
        list(tickers),
        period=period,
        interval=interval,
        auto_adjust=True,
        group_by="column",
        progress=False,
        threads=True,
    )
    if raw is None or raw.empty:
        return {v: pd.DataFrame() for v in FIELDS.values()}

    panel: Panel = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for src, dst in FIELDS.items():
            df = raw[src] if src in raw.columns.get_level_values(0) else pd.DataFrame()
            panel[dst] = df.dropna(axis=1, how="all")
    else:  # single ticker comes back with flat columns
        t = tickers[0]
        for src, dst in FIELDS.items():
            col = raw[src] if src in raw.columns else pd.Series(dtype=float)
            panel[dst] = col.to_frame(name=t).dropna(axis=1, how="all")

    # keep only tickers that have close prices, aligned across all fields
    good = panel["close"].columns
    for k in panel:
        panel[k] = panel[k].reindex(columns=good)
    return panel


def latest_quotes(tickers: list[str]) -> pd.DataFrame:
    """Freshest available price per ticker from intraday 5m bars.

    Returns a DataFrame indexed by ticker with columns [last, as_of].
    Falls back to an empty frame on any failure; callers should then use
    the last daily close instead.
    """
    try:
        raw = yf.download(
            list(tickers),
            period="1d",
            interval="5m",
            auto_adjust=True,
            group_by="column",
            progress=False,
            threads=True,
        )
        if raw is None or raw.empty:
            return pd.DataFrame(columns=["last", "as_of"])
        close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].set_axis(
            [tickers[0]], axis=1
        )
        last = close.ffill().iloc[-1]
        as_of = close.apply(lambda s: s.last_valid_index())
        out = pd.DataFrame({"last": last, "as_of": as_of}).dropna(subset=["last"])
        return out
    except Exception:
        return pd.DataFrame(columns=["last", "as_of"])


def daily_returns(close: pd.DataFrame) -> pd.DataFrame:
    return close.pct_change().dropna(how="all")


def ticker_profile(ticker: str) -> dict:
    """Company profile facts from Yahoo (best-effort, empty dict on failure).

    Keys: name, sector, industry, market_cap, trailing_pe, forward_pe,
    dividend_yield, beta, avg_volume. dividend_yield is in percent."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        return {}
    if not isinstance(info, dict) or not info:
        return {}
    dy = info.get("dividendYield")
    # yfinance has reported this both as a fraction (0.004) and percent (0.4)
    if dy is not None and dy < 0.2:
        dy = dy * 100
    return {
        "name": info.get("longName") or info.get("shortName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "dividend_yield": dy,
        "beta": info.get("beta"),
        "avg_volume": info.get("averageVolume"),
    }


# ------------------------------------------------ catalyst data (best-effort)
# All of these degrade to empty results on any failure: catalyst attribution
# is optional color, never worth failing a request over.

def earnings_dates(ticker: str) -> list[pd.Timestamp]:
    """Past and upcoming earnings dates, normalized to naive midnight."""
    try:
        df = yf.Ticker(ticker).get_earnings_dates(limit=16)
        if df is None or df.empty:
            return []
        idx = pd.DatetimeIndex(df.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        return sorted(set(idx.normalize()))
    except Exception:
        return []


def corporate_actions(ticker: str) -> pd.DataFrame:
    """Dividends and splits indexed by ex-date (empty frame on failure)."""
    try:
        acts = yf.Ticker(ticker).actions
        if acts is None or acts.empty:
            return pd.DataFrame()
        if isinstance(acts.index, pd.DatetimeIndex) and acts.index.tz is not None:
            acts.index = acts.index.tz_localize(None)
        return acts
    except Exception:
        return pd.DataFrame()


def recent_news(ticker: str) -> list[dict]:
    """Recent headlines as [{when, title, publisher, url}], newest first.

    Handles both the legacy flat yfinance news shape and the newer
    'content'-nested one. Coverage is only the last few weeks.
    """
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for item in items:
        c = item.get("content", item)
        title = c.get("title")
        ts = c.get("pubDate") or item.get("providerPublishTime")
        if not title or ts is None:
            continue
        try:
            when = (pd.to_datetime(ts, unit="s", utc=True) if isinstance(ts, (int, float))
                    else pd.to_datetime(ts, utc=True)).tz_convert(None)
        except Exception:
            continue
        provider = c.get("provider") or {}
        url = (c.get("canonicalUrl") or {}).get("url") if isinstance(c.get("canonicalUrl"), dict) else item.get("link")
        out.append({
            "when": when,
            "title": str(title),
            "publisher": provider.get("displayName") or item.get("publisher") or "",
            "url": url,
        })
    out.sort(key=lambda n: n["when"], reverse=True)
    return out
