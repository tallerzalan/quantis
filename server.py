"""Quantis API server: FastAPI wrapper around the src/quantis quant core,
serving the built React frontend from frontend/dist.

Run:  python serve.py   (or: uvicorn server:app --port 8000)
"""
from __future__ import annotations

import sys
import time
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from quantis import backtest as bt
from quantis import custom as cst
from quantis import data as dat
from quantis import events as evt
from quantis import factors as fac
from quantis import indicators as ind
from quantis import interpret as itp
from quantis import montecarlo as mc
from quantis import optimize as opt
from quantis import portfolio as pf
from quantis import risk as rsk
from quantis import signals as sig
from quantis import strategies as strat
from quantis import universe as uni
from quantis import watchlist as wl

app = FastAPI(title="Quantis API")

CONTEXT = {"SPY", "QQQ", "IWM"}  # always fetched for benchmark/regime
HISTORY_TTL, QUOTES_TTL = 300, 120
_cache: dict = {}


def _cached(key, ttl, fn):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (now, value)
    return value


def clean(obj):
    """Recursively make JSON-safe: NaN/inf -> None, numpy -> python."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj) if np.isfinite(obj) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.strftime("%Y-%m-%d")
    return obj


def get_panel(period: str = "1y"):
    tickers = sorted(set(wl.load()) | CONTEXT)
    return _cached(("panel", tuple(tickers), period), HISTORY_TTL,
                   lambda: dat.download_history(tickers, period))


def get_quotes():
    tickers = sorted(set(wl.load()) | CONTEXT)
    return _cached(("quotes", tuple(tickers)), QUOTES_TTL,
                   lambda: dat.latest_quotes(tickers))


def last_prices(panel):
    quotes = get_quotes()
    last = panel["close"].iloc[-1].copy()
    if not quotes.empty:
        for t in last.index:
            v = quotes["last"].get(t, np.nan)
            if np.isfinite(v):
                last[t] = v
    return last


def watch_only(panel):
    cols = [t for t in wl.load() if t in panel["close"].columns]
    return {k: v[cols] for k, v in panel.items()}


def market_regime(panel):
    close = panel["close"]
    spy = close["SPY"].dropna()
    spy_up = bool(spy.iloc[-1] > spy.ewm(span=50, adjust=False).mean().iloc[-1])
    watch = close[[t for t in wl.load() if t in close.columns]]
    ema20 = watch.ewm(span=20, adjust=False).mean()
    breadth = float((watch.iloc[-1] > ema20.iloc[-1]).mean())
    return itp.regime(spy_up, breadth)


def as_of(panel):
    quotes = get_quotes()
    if not quotes.empty and quotes["as_of"].notna().any():
        return str(quotes["as_of"].max())
    return str(panel["close"].index[-1].date())


# ------------------------------------------------------------------ watchlist

@app.get("/api/watchlist")
def api_watchlist():
    return {"tickers": [{"symbol": t, "group": wl.group_of(t)} for t in wl.load()]}


@app.post("/api/watchlist/add")
def api_watchlist_add(payload: dict = Body(...)):
    t = str(payload.get("ticker", "")).upper().strip()
    if not t:
        raise HTTPException(400, "No ticker given.")
    if t not in wl.load():
        probe = dat.download_history([t], period="3mo")
        if probe["close"].empty or t not in probe["close"].columns:
            raise HTTPException(404, f"Couldn't find price data for '{t}'. Check the symbol.")
        wl.add(t)
        _cache.clear()
    return api_watchlist()


@app.post("/api/watchlist/remove")
def api_watchlist_remove(payload: dict = Body(...)):
    wl.remove(str(payload.get("ticker", "")))
    _cache.clear()
    return api_watchlist()


@app.post("/api/watchlist/reset")
def api_watchlist_reset():
    wl.reset()
    _cache.clear()
    return api_watchlist()


@app.get("/api/search")
def api_search(q: str = Query(..., min_length=1)):
    try:
        res = yf.Search(q, max_results=8)
        out = [
            {
                "symbol": item.get("symbol"),
                "name": item.get("shortname") or item.get("longname") or "",
                "exchange": item.get("exchDisp", ""),
                "type": item.get("quoteType", ""),
            }
            for item in res.quotes
            if item.get("symbol") and item.get("quoteType") in ("EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY")
        ]
        return {"results": out}
    except Exception:
        return {"results": []}


# --------------------------------------------------------------------- market

@app.get("/api/market")
def api_market(period: str = "1y"):
    panel = get_panel(period)
    if panel["close"].empty:
        raise HTTPException(503, "No market data — check your internet connection.")
    wpanel = watch_only(panel)
    close = wpanel["close"]
    last = last_prices(panel)
    feats = sig.edge_scores(sig.compute_features(wpanel))
    prev = close.iloc[-2] if len(close) > 1 else close.iloc[-1]
    dollar_vol = (close * wpanel["volume"]).rolling(20).mean().iloc[-1]

    rows = []
    for t in close.columns:
        f = feats.loc[t] if t in feats.index else None
        rows.append(
            {
                "ticker": t,
                "group": wl.group_of(t),
                "last": last.get(t),
                "chg1": (last.get(t) / prev.get(t) - 1) * 100 if prev.get(t) else None,
                "chg5": f["roc5"] if f is not None else None,
                "chg20": f["roc20"] if f is not None else None,
                "rsi14": f["rsi14"] if f is not None else None,
                "rvol": f["rvol"] if f is not None else None,
                "edge": f["edge"] if f is not None else None,
                "dollar_vol": dollar_vol.get(t),
            }
        )
    indices = [
        {"ticker": t, "last": last.get(t), "chg": (last.get(t) / panel["close"][t].iloc[-2] - 1) * 100}
        for t in ["SPY", "QQQ", "IWM"]
        if t in panel["close"].columns and len(panel["close"][t].dropna()) > 1
    ]
    missing = sorted(set(wl.load()) - set(close.columns))
    return clean({
        "as_of": as_of(panel),
        "regime": market_regime(panel),
        "indices": indices,
        "rows": rows,
        "missing": missing,
    })


@app.get("/api/ideas")
def api_ideas(capital: float = 100.0, period: str = "1y"):
    panel = get_panel(period)
    wpanel = watch_only(panel)
    scored = sig.edge_scores(sig.compute_features(wpanel))
    if scored.empty:
        raise HTTPException(503, "Not enough data to score your watchlist.")
    ideas = sig.trade_ideas(scored, capital=capital, n=min(5, len(scored)))
    last = last_prices(panel)
    close = wpanel["close"]
    out = []
    for t, row in ideas.iterrows():
        entry = float(last.get(t, row["entry"]))
        risk = 1.5 * row["atr"]
        spark = close[t].dropna().iloc[-30:]
        out.append(
            {
                "ticker": t,
                "group": wl.group_of(t),
                "entry": entry,
                "stop": entry - risk,
                "target": entry + 2 * risk,
                "risk_pct": 100 * risk / entry if entry else None,
                "dollars": row["dollars"],
                "weight": row["weight"],
                "edge": row["edge"],
                "hold": row["hold_days"],
                "reason": itp.idea_reason(row),
                "spark": [{"time": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in spark.items()],
            }
        )
    ranked = [
        {"ticker": t, "edge": r["edge"], "momentum": r["momentum"], "trend": r["trend"],
         "meanrev": r["meanrev"], "volume": r["volume_score"], "chg20": r["roc20"]}
        for t, r in scored.iterrows()
    ]
    return clean({"as_of": as_of(panel), "regime": market_regime(panel),
                  "capital": capital, "ideas": out, "ranked": ranked})


# ---------------------------------------------------------------------- chart

@app.get("/api/chart/{ticker}")
def api_chart(ticker: str, period: str = "1y"):
    ticker = ticker.upper()
    panel = get_panel(period)
    if ticker not in panel["close"].columns:
        probe = dat.download_history([ticker], period=period)
        if probe["close"].empty:
            raise HTTPException(404, f"No data for {ticker}.")
        panel = probe
    idx = panel["close"][ticker].dropna().index
    candles = [
        {
            "time": d.strftime("%Y-%m-%d"),
            "open": float(panel["open"][ticker].get(d)),
            "high": float(panel["high"][ticker].get(d)),
            "low": float(panel["low"][ticker].get(d)),
            "close": float(panel["close"][ticker].get(d)),
            "volume": float(panel["volume"][ticker].get(d, 0) or 0),
        }
        for d in idx
    ]
    close = panel["close"][ticker].dropna()
    volume = panel["volume"][ticker].reindex(close.index)
    e20 = close.ewm(span=20, adjust=False).mean()
    e50 = close.ewm(span=50, adjust=False).mean()
    series = lambda s: [{"time": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in s.dropna().items()]

    # indicator series: Bollinger(20,2), RSI-14, MACD(12,26,9), volume MA + rvol
    mid = close.rolling(20).mean()
    sd = close.rolling(20).std()
    frame = close.to_frame("x")
    rsi14 = ind.rsi(frame, 14)["x"]
    macd_line, macd_sig, macd_hist = (s["x"] for s in ind.macd(frame))
    vol_ma = volume.rolling(20).mean()
    rvol = volume / vol_ma.shift(1)
    pctb = ind.bollinger_percent_b(frame)["x"]

    readouts = {
        "rsi": itp.rsi_verdict(float(rsi14.iloc[-1])),
        "macd": itp.macd_verdict(float(macd_hist.iloc[-1]),
                                 float(macd_hist.iloc[-2]) if len(macd_hist) > 1 else None),
        "bollinger": itp.bollinger_verdict(float(pctb.iloc[-1])),
        "volume": itp.volume_verdict(float(rvol.iloc[-1])),
    }

    rets = close.pct_change().dropna()
    bench = get_panel(period)["close"]["SPY"].pct_change().dropna()
    beta, alpha = bt.beta_alpha(rets, bench)
    metrics = {
        "beta": beta,
        "alpha": alpha,
        "sharpe": rsk.sharpe_ratio(rets),
        "volatility": rsk.annualized_vol(rets),
        "var_95": rsk.hist_var(rets),
        "max_drawdown": bt.max_drawdown((1 + rets).cumprod()),
        "chg1": float(close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) > 1 else None,
        "total_period": float(close.iloc[-1] / close.iloc[0] - 1) * 100,
    }
    rvol_by_time = {d.strftime("%Y-%m-%d"): float(v) for d, v in rvol.dropna().items()}
    for c in candles:
        c["rvol"] = rvol_by_time.get(c["time"])
    return clean({
        "ticker": ticker,
        "candles": candles,
        "ema20": series(e20),
        "ema50": series(e50),
        "bb_upper": series(mid + 2 * sd),
        "bb_lower": series(mid - 2 * sd),
        "bb_mid": series(mid),
        "rsi14": series(rsi14),
        "macd_line": series(macd_line),
        "macd_signal": series(macd_sig),
        "macd_hist": series(macd_hist),
        "vol_ma": series(vol_ma),
        "readouts": readouts,
        "metrics": metrics,
        "verdicts": {
            "beta": itp.beta_verdict(beta),
            "alpha": itp.alpha_verdict(alpha),
            "sharpe": itp.sharpe_verdict(metrics["sharpe"]),
            "drawdown": itp.drawdown_verdict(metrics["max_drawdown"]),
        },
        "in_watchlist": ticker in wl.load(),
    })


# ------------------------------------------------------- events & forecasting

def ticker_series(ticker: str, period: str):
    """(close, volume, high, low, bench_close) for any ticker; 404 if unknown."""
    panel = get_panel(period)
    if ticker not in panel["close"].columns:
        panel = _cached(("probe", ticker, period), HISTORY_TTL,
                        lambda: dat.download_history([ticker], period))
        if panel["close"].empty or ticker not in panel["close"].columns:
            raise HTTPException(404, f"No data for {ticker}.")
    close, volume = panel["close"][ticker], panel["volume"][ticker]
    high, low = panel["high"][ticker], panel["low"][ticker]
    base = get_panel(period)
    bench = base["close"]["SPY"] if "SPY" in base["close"].columns else None
    return close.dropna(), volume, high, low, bench


def catalyst_data(ticker: str):
    return _cached(("catalyst", ticker), 3600, lambda: {
        "earnings": dat.earnings_dates(ticker),
        "actions": dat.corporate_actions(ticker),
        "news": dat.recent_news(ticker),
    })


@app.get("/api/events/{ticker}")
def api_events(ticker: str, period: str = "1y", z: float = 2.5):
    ticker = ticker.upper()
    close, volume, _, _, bench = ticker_series(ticker, period)
    moves = evt.move_significance(close, volume, z_thresh=max(1.5, min(z, 5.0)))
    cat = catalyst_data(ticker)
    events = evt.attribute_events(moves, close.index, earnings=cat["earnings"],
                                  actions=cat["actions"], news=cat["news"], bench_close=bench)
    out, markers = [], []
    for ev in reversed(events):  # newest first
        story = itp.event_story(ev, ticker)
        out.append({**ev, **story,
                    "headlines": [{"title": n["title"], "publisher": n["publisher"],
                                   "url": n["url"], "when": n["when"]} for n in ev["headlines"]]})
        up = ev["direction"] == "up"
        markers.append({
            "time": ev["date"].strftime("%Y-%m-%d"),
            "position": "belowBar" if up else "aboveBar",
            "shape": "arrowUp" if up else "arrowDown",
            "color": "#3987e5" if up else "#e66767",
            "text": f"{ev['ret'] * 100:+.1f}%",
        })
    markers.reverse()  # chart wants oldest first
    return clean({
        "ticker": ticker,
        "events": out,
        "markers": markers,
        "params": {"z_threshold": max(1.5, min(z, 5.0)), "vol_span": evt.VOL_SPAN,
                   "min_abs_move_pct": evt.MIN_ABS_RET * 100},
        "note": ("A day counts as significant when its move is at least "
                 f"{max(1.5, min(z, 5.0)):.1f}× the stock's own recent daily volatility "
                 f"(a {evt.VOL_SPAN}-day EWMA, measured up to the prior day) AND at least "
                 f"{evt.MIN_ABS_RET * 100:.0f}% in size."),
    })


@app.get("/api/forecast/{ticker}")
def api_forecast(ticker: str, period: str = "1y", horizon: int = 21,
                 paths: int = 2000, dip: float = 5.0, target: float = 10.0, stop: float = 7.0,
                 vol_mode: str = "current"):
    ticker = ticker.upper()
    horizon = max(5, min(horizon, 126))
    paths = max(200, min(paths, 10000))
    vol_mode = vol_mode if vol_mode in ("current", "history") else "current"
    dip_f, target_f, stop_f = (max(0.5, min(x, 30.0)) / 100 for x in (dip, target, stop))

    close, volume, _, _, _ = ticker_series(ticker, period)
    rets = close.pct_change().dropna()
    last = float(close.iloc[-1])
    last_date = close.index[-1]

    seed = zlib.crc32(f"{ticker}:{last_date.date()}".encode())
    try:
        sims = mc.simulate_paths(rets, horizon=horizon, n_paths=paths, seed=seed, vol_mode=vol_mode)
        dist = mc.sample_stats(rets)
    except ValueError as e:
        raise HTTPException(422, str(e))

    fan = mc.fan_bands(sims, last)
    future = pd.bdate_range(last_date, periods=horizon + 1)  # includes today as day 0
    fan_rows = [{"time": d.strftime("%Y-%m-%d"), **{k: float(fan.iloc[i][k]) for k in fan.columns}}
                for i, d in enumerate(future)]
    summary = mc.summarize(sims)
    dip_grid = mc.dip_probabilities(sims, [0.02, 0.03, 0.05, 0.08, 0.10])
    best = mc.best_entry(sims)
    strat = mc.dip_buy_outcomes(sims, dip=dip_f, target=target_f, stop=stop_f)

    # current dip context for the timing verdict
    rsi14 = float(ind.rsi(close.to_frame("x"), 14)["x"].iloc[-1])
    pctb = float(ind.bollinger_percent_b(close.to_frame("x"))["x"].iloc[-1])
    ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
    off_high = last / float(close.iloc[-20:].max()) - 1
    cat = catalyst_data(ticker)
    next_earn = next((e for e in cat["earnings"] if e > last_date), None)
    earnings_in = int(np.busday_count(last_date.date(), next_earn.date())) if next_earn is not None else None
    verdict = itp.entry_verdict({
        "rsi14": rsi14, "pctb": pctb, "off_high": off_high,
        "above_ema50": last > ema50,
        "earnings_in": earnings_in if earnings_in is not None and earnings_in <= horizon else None,
    })

    limit_price = last * best["median_low"]
    fill_prob = mc.dip_probabilities(sims, [1 - best["median_low"]])[1 - best["median_low"]]
    history = close.iloc[-60:]
    return clean({
        "ticker": ticker,
        "last": last,
        "horizon": horizon,
        "n_paths": paths,
        "history": [{"time": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in history.items()],
        "fan": fan_rows,
        "summary": summary,
        "dip_odds": [{"dip": d, "prob": p} for d, p in sorted(dip_grid.items())],
        "best_entry": best,
        "strategy": {**strat, "params": {"dip": dip_f, "target": target_f, "stop": stop_f}},
        "verdict": verdict,
        "plan": {
            "limit_price": limit_price,
            "fill_prob": fill_prob,
            "median_day": best["median_day"],
            "p75_day": best["p75_day"],
        },
        "next_earnings": next_earn,
        "earnings_in": earnings_in,
        "narrative": itp.forecast_narrative(ticker, horizon, paths, summary, best, strat, dip_f * 100),
        "dist": dist,
        "vol_line": itp.vol_regime_line(dist),
        "params": {
            "n_paths": paths,
            "horizon": horizon,
            "block": mc.DEFAULT_BLOCK,
            "vol_mode": vol_mode,
            "vol_span": mc.VOL_SPAN,
            "sample_days": dist["n_days"],
            "method": "circular block bootstrap of real daily returns"
                      + (", rescaled to today's volatility" if vol_mode == "current" else ""),
        },
    })


@app.get("/api/facts/{ticker}")
def api_facts(ticker: str, period: str = "1y"):
    ticker = ticker.upper()
    close, volume, high, low, bench = ticker_series(ticker, period)
    profile = _cached(("profile", ticker), 3600, lambda: dat.ticker_profile(ticker))
    rets = close.pct_change().dropna()
    last = float(close.iloc[-1])
    atr = ind.atr(high.to_frame("x"), low.to_frame("x"), close.to_frame("x"))["x"].iloc[-1]
    beta = None
    if bench is not None:
        beta, _ = bt.beta_alpha(rets, bench.pct_change().dropna())
    extras = {
        "last": last,
        "year_high": float(close.max()),
        "year_low": float(close.min()),
        "atr_pct": float(atr / last * 100) if np.isfinite(atr) and last else None,
        "dollar_vol": float((close * volume).rolling(20).mean().iloc[-1]),
        "beta": beta,
    }
    dist = mc.sample_stats(rets) if len(rets) >= 30 else {}
    cat = catalyst_data(ticker)
    next_earn = next((e for e in cat["earnings"] if e > close.index[-1]), None)
    return clean({
        "ticker": ticker,
        "name": profile.get("name") or ticker,
        "sheet": itp.facts_sheet(profile, extras),
        "vol_line": itp.vol_regime_line(dist) if dist else "",
        "next_earnings": next_earn,
    })


@app.get("/api/universes")
def api_universes():
    return {"universes": [{"key": "watchlist", "name": "My watchlist"}]
            + [{"key": g, "name": g} for g in uni.UNIVERSE]}


# ------------------------------------------------------------------- backtest

@app.get("/api/strategies")
def api_strategies():
    return {"strategies": strat.registry_meta(),
            "examples": cst.EXAMPLES, "template": cst.TEMPLATE}


@app.post("/api/backtest")
def api_backtest(payload: dict = Body(...)):
    p = payload.get("params", {})
    period = p.get("period", "1y")
    capital = float(p.get("capital", 100))
    panel = get_panel(period)
    universe = payload.get("universe") or "watchlist"
    if universe == "watchlist":
        wpanel, uni_name = watch_only(panel), "My watchlist"
    elif universe in uni.UNIVERSE:
        wpanel = _cached(("basket", universe, period), HISTORY_TTL,
                         lambda: dat.download_history(uni.UNIVERSE[universe], period))
        uni_name = universe
    else:
        raise HTTPException(400, f"Unknown basket '{universe}'.")
    if wpanel["close"].empty:
        raise HTTPException(503, f"No data for {uni_name}.")
    bench_close = panel["close"]["SPY"].dropna()
    bench_rets = bench_close.pct_change().dropna()

    code = payload.get("code")
    key = payload.get("strategy", "momentum")
    trades = None
    try:
        if code:
            name = "Your custom strategy"
            entries, exits = cst.run_user_strategy(code, wpanel)
            cfg = bt.TradeConfig(
                stop_atr_mult=float(p.get("stop_mult", 1.5)),
                max_hold_days=int(p.get("hold_days", 7)),
                max_positions=int(p.get("top_n", 5)),
                slippage_bps=float(p.get("slippage", 5)),
                spread_bps=float(p.get("spread", 2)),
                commission_bps=float(p.get("commission", 1)),
                capital=capital,
            )
            equity, trades = bt.run_signal_trades(wpanel, entries, exits, cfg)
        elif key == "momentum" :
            name = strat.STRATEGIES[key]["name"]
            equity, _ = bt.run_rebalance(
                wpanel["close"], lookback=int(p.get("lookback", 20)),
                top_n=int(p.get("top_n", 5)), hold_days=int(p.get("hold_days", 5)),
                slippage_bps=float(p.get("slippage", 5)),
                spread_bps=float(p.get("spread", 2)),
                commission_bps=float(p.get("commission", 1)), capital=capital,
            )
        else:
            if key not in strat.STRATEGIES:
                raise HTTPException(400, f"Unknown strategy '{key}'.")
            name = strat.STRATEGIES[key]["name"]
            entries, exits = strat.STRATEGIES[key]["builder"](wpanel)
            cfg = bt.TradeConfig(
                stop_atr_mult=float(p.get("stop_mult", 1.5)),
                max_hold_days=int(p.get("hold_days", 7)),
                max_positions=int(p.get("top_n", 5)),
                slippage_bps=float(p.get("slippage", 5)),
                spread_bps=float(p.get("spread", 2)),
                commission_bps=float(p.get("commission", 1)),
                capital=capital,
            )
            equity, trades = bt.run_signal_trades(wpanel, entries, exits, cfg)
    except cst.StrategyError as e:
        raise HTTPException(422, str(e))

    if equity.dropna().empty:
        raise HTTPException(422, "The backtest produced no equity curve on this window.")
    stats = bt.perf_stats(equity, bench_returns=bench_rets, trades=trades)
    bench_eq = bt.buy_hold_equity(bench_close.reindex(equity.index).dropna(), capital)
    bench_total = float(bench_eq.iloc[-1] / bench_eq.iloc[0] - 1) if len(bench_eq) else None
    points = lambda s: [{"time": d.strftime("%Y-%m-%d"), "value": float(v)} for d, v in s.dropna().items()]

    # robustness: reshuffle the strategy's own daily returns into alternate
    # histories — was this result skill, or one lucky ordering of days?
    strat_rets = equity.pct_change().dropna()
    mcarlo = None
    if len(strat_rets) >= 40:
        try:
            mcarlo = mc.equity_confidence(
                strat_rets, capital=capital, n_paths=1000,
                seed=zlib.crc32(f"{name}:{uni_name}:{period}:{len(strat_rets)}".encode()),
                bench_total=bench_total)
            mcarlo["narrative"] = itp.robustness_narrative(mcarlo, capital)
        except ValueError:
            mcarlo = None
    trade_rows = [
        {**t, "entry_date": str(pd.Timestamp(t["entry_date"]).date()),
         "signal_date": str(pd.Timestamp(t["signal_date"]).date()),
         "exit_date": str(pd.Timestamp(t["exit_date"]).date())}
        for t in (trades or [])[-100:]
    ]
    return clean({
        "name": name,
        "universe": uni_name,
        "tickers": list(wpanel["close"].columns),
        "equity": points(equity),
        "bench": points(bench_eq),
        "stats": stats,
        "summary": itp.backtest_summary(stats, capital, bench_total),
        "montecarlo": mcarlo,
        "trades": trade_rows,
    })


# ------------------------------------------------------------------- optimize

@app.post("/api/optimize")
def api_optimize(payload: dict = Body(default={})):
    period = payload.get("period", "1y")
    capital = float(payload.get("capital", 100))
    cap = float(payload.get("cap", 0.4))
    rf = float(payload.get("rf", 0.04))
    panel = get_panel(period)
    wpanel = watch_only(panel)
    tickers = payload.get("tickers")
    if not tickers:
        scored = sig.edge_scores(sig.compute_features(wpanel))
        tickers = list(scored.head(8).index)
    tickers = [t for t in tickers if t in wpanel["close"].columns]
    if len(tickers) < 2:
        raise HTTPException(400, "Pick at least two tickers with data.")
    rets = wpanel["close"][tickers].pct_change().dropna()
    if len(rets) < 60:
        raise HTTPException(422, "Need at least ~3 months of overlapping history.")
    mu = opt.expected_returns(rets)
    cov = opt.shrunk_covariance(rets)

    w_ms, fell_back = opt.max_sharpe(mu, cov, cap=cap, rf=rf)
    w_mv = opt.min_variance(cov, cap=cap)
    s_ms = opt.portfolio_stats(w_ms, mu, cov, rf)
    s_mv = opt.portfolio_stats(w_mv, mu, cov, rf)

    def profile(name, blurb, w, s, fb=False):
        dollars = opt.dollar_allocation(w, capital).to_dict()
        return {
            "name": name, "blurb": blurb,
            "weights": {k: float(v) for k, v in w.items() if v > 0.005},
            "dollars": dollars,
            "stats": s,
            "summary": itp.optimizer_summary(name, s, dollars, fb, capital),
        }

    # balanced: min-vol portfolio targeting the midpoint return between the two
    mid = (s_mv["return"] + s_ms["return"]) / 2
    S, m = cov.values, mu.values
    w_bal_arr = opt._solve(
        lambda w: w @ S @ w, len(mu), cap,
        extra_constraints=[{"type": "eq", "fun": lambda w, t=mid: w @ m - t}],
    )
    w_bal = pd.Series(w_bal_arr, index=mu.index).clip(lower=0)
    s_bal = opt.portfolio_stats(w_bal, mu, cov, rf)

    # Black-Litterman: equilibrium prior (equal-weight market proxy) blended with
    # Quantis's own expected-return views. Max-Sharpe on the posterior returns.
    bench_ret = panel["close"]["SPY"].pct_change().dropna()
    bvar = float(bench_ret.var(ddof=0)) * opt.TRADING_DAYS
    delta = float(np.clip((bench_ret.mean() * opt.TRADING_DAYS - rf) / bvar, 1.5, 5.0)) if bvar > 0 else 2.5
    w_mkt = pd.Series(1.0 / len(tickers), index=mu.index)
    mu_bl = opt.black_litterman(cov, w_mkt, views=mu, delta=delta)
    w_bl, bl_fb = opt.max_sharpe(mu_bl, cov, cap=cap, rf=rf)
    s_bl = opt.portfolio_stats(w_bl, mu_bl, cov, rf)

    frontier = opt.efficient_frontier(mu, cov, cap=cap)
    vols = np.sqrt(np.diag(cov.values))
    return clean({
        "tickers": tickers,
        "capital": capital,
        "profiles": [
            profile("Cautious", "Smallest swings: the minimum-variance mix.", w_mv, s_mv),
            profile("Balanced", "Middle path between calm and growth.", w_bal, s_bal),
            profile("Bold", "Best risk-adjusted growth: the max-Sharpe mix.", w_ms, s_ms, fell_back),
            profile("Anchored", "Black-Litterman: market equilibrium tilted by Quantis's views.", w_bl, s_bl, bl_fb),
        ],
        "black_litterman": {"delta": delta, "note": itp.bl_summary(delta)},
        "frontier": frontier.to_dict("records"),
        "assets": [{"ticker": t, "ret": float(mu[t]), "vol": float(vols[i])} for i, t in enumerate(mu.index)],
        "fell_back": fell_back,
    })


# ----------------------------------------------------------------------- risk

@app.get("/api/risk")
def api_risk(period: str = "1y"):
    panel = get_panel(period)
    wpanel = watch_only(panel)
    rets = wpanel["close"].pct_change().dropna(how="all")
    bench = panel["close"]["SPY"].pct_change().dropna()
    table = rsk.summary_table(rets, bench)
    rows = [
        {"ticker": t, **{k: row[k] for k in table.columns},
         "beta_level": itp.beta_verdict(row["beta"])["level"],
         "sharpe_level": itp.sharpe_verdict(row["sharpe"])["level"]}
        for t, row in table.iterrows()
    ]
    return clean({"rows": rows, "info": itp.METRIC_INFO})


@app.get("/api/correlation")
def api_correlation(tickers: str = "", period: str = "1y"):
    panel = get_panel(period)
    wpanel = watch_only(panel)
    want = [t.strip().upper() for t in tickers.split(",") if t.strip()] or list(wpanel["close"].columns[:12])
    cols = [t for t in want if t in wpanel["close"].columns]
    corr = wpanel["close"][cols].pct_change().dropna().corr()
    return clean({"tickers": cols, "matrix": [[float(corr.iloc[i, j]) for j in range(len(cols))] for i in range(len(cols))]})


@app.get("/api/risk/detail/{ticker}")
def api_risk_detail(ticker: str, period: str = "1y"):
    """Rolling beta + underwater drawdown series for one ticker."""
    ticker = ticker.upper()
    panel = get_panel(period)
    close = panel["close"]
    if ticker in close.columns:
        px = close[ticker]
    else:
        px = ticker_series(ticker, period)["close"].get(ticker)
        if px is None or px.dropna().empty:
            raise HTTPException(404, f"No data for {ticker}.")
    r = px.pct_change().dropna()
    bench = close["SPY"].pct_change().dropna()
    rb = rsk.rolling_beta(r, bench)
    equity = (1 + r).cumprod()
    underwater = equity / equity.cummax() - 1
    return clean({
        "ticker": ticker,
        "rolling_beta": [{"date": d.strftime("%Y-%m-%d"), "beta": float(v)} for d, v in rb.items()],
        "drawdown": [{"date": d.strftime("%Y-%m-%d"), "dd": float(v)} for d, v in underwater.items()],
    })


# -------------------------------------------------------------------- factors

@app.get("/api/factors")
def api_factors(period: str = "1y"):
    """Per-ticker factor exposures, watchlist aggregate, and sector allocation."""
    panel = get_panel(period)
    wpanel = watch_only(panel)
    tickers = list(wpanel["close"].columns)
    if not tickers:
        raise HTTPException(422, "Add tickers to your watchlist first.")
    fpanel = _cached(f"factor_etfs:{period}", HISTORY_TTL,
                     lambda: dat.download_history(fac.FACTOR_TICKERS, period))
    facs = fac.factor_returns(fpanel["close"])
    if facs.empty:
        raise HTTPException(503, "Factor proxy data is unavailable right now.")
    rets = wpanel["close"].pct_change().dropna(how="all")
    names = list(facs.columns)
    table = fac.exposure_table(rets, facs)
    rows = []
    for t, row in table.iterrows():
        betas = {f: float(row[f]) for f in names if f in row.index}
        exp = {"betas": betas, "alpha": float(row["alpha"]), "r2": float(row["r2"])}
        rows.append({"ticker": t, **exp, "summary": itp.factor_summary(exp)})
    rows.sort(key=lambda r: -abs(r["betas"].get("market", 0)))

    w = pd.Series(1.0 / len(tickers), index=tickers)
    agg = fac.portfolio_exposures(w, rets, facs)
    sectors = {t: _cached(f"sector:{t}", 86400, lambda t=t: (dat.ticker_profile(t) or {}).get("sector"))
               for t in tickers}
    alloc = fac.sector_allocation({t: 1.0 / len(tickers) for t in tickers}, sectors)
    return clean({
        "factors": names,
        "labels": fac.FACTOR_LABELS,
        "rows": rows,
        "portfolio": {**agg, "summary": itp.factor_summary(agg)},
        "sectors": alloc,
        "sector_summary": itp.sector_summary(alloc),
        "info": itp.METRIC_INFO,
    })


# ------------------------------------------------------------------ portfolio

def _portfolio_payload():
    panel = get_panel("1y")
    last = last_prices(panel)
    state = pf.load()
    val = pf.valuation(state, last)
    total = state["cash"] + (float(val["value"].sum()) if not val.empty else 0.0)
    payload = {
        "cash": state["cash"],
        "total": total,
        "start": 100.0,
        "positions": val.to_dict("records") if not val.empty else [],
        "metrics": None,
        "verdicts": None,
    }
    if not val.empty:
        w = pf.weights(state, last)
        rets = panel["close"].pct_change().dropna(how="all")
        bench = panel["close"]["SPY"].pct_change().dropna()
        m = rsk.portfolio_risk(w, rets, bench)
        if m:
            m.pop("daily_returns", None)
            payload["metrics"] = m
            payload["verdicts"] = {
                "beta": itp.beta_verdict(m["beta"]),
                "alpha": itp.alpha_verdict(m["alpha"]),
                "sharpe": itp.sharpe_verdict(m["sharpe"]),
            }
            payload["var_sentence"] = itp.var_sentence(m.get("var_95"), total)
    return clean(payload)


@app.get("/api/portfolio")
def api_portfolio():
    return _portfolio_payload()


@app.post("/api/portfolio/buy")
def api_portfolio_buy(payload: dict = Body(...)):
    t = str(payload.get("ticker", "")).upper().strip()
    dollars = float(payload.get("dollars", 0))
    if not t or dollars <= 0:
        raise HTTPException(400, "Need a ticker and a positive dollar amount.")
    panel = get_panel("1y")
    last = last_prices(panel)
    price = float(payload.get("price") or last.get(t, np.nan))
    if not np.isfinite(price) or price <= 0:
        raise HTTPException(404, f"No live price for {t} — is it in your watchlist?")
    state = pf.add_position(pf.load(), t, dollars / price, price)
    pf.save(state)
    return _portfolio_payload()


@app.post("/api/portfolio/sell")
def api_portfolio_sell(payload: dict = Body(...)):
    t = str(payload.get("ticker", "")).upper().strip()
    panel = get_panel("1y")
    last = last_prices(panel)
    price = float(last.get(t, np.nan))
    if not np.isfinite(price):
        raise HTTPException(404, f"No live price for {t}.")
    state = pf.remove_position(pf.load(), t, price)
    pf.save(state)
    return _portfolio_payload()


@app.post("/api/portfolio/reset")
def api_portfolio_reset():
    pf.save({"cash": 100.0, "positions": []})
    return _portfolio_payload()


@app.get("/api/info")
def api_info():
    return {"metrics": itp.METRIC_INFO}


# ------------------------------------------------------------------- frontend

dist = Path(__file__).parent / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
