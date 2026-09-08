"""Built-in strategy registry: entry/exit builders + human descriptions.

Every builder takes a panel and returns (entries, exits) boolean DataFrames.
The event-loop engine (backtest.run_signal_trades) adds stops and timeouts;
"Momentum (top-N)" uses the vectorized rebalance engine instead.
"""
from __future__ import annotations

import pandas as pd

from . import backtest as bt
from . import indicators as ind


def donchian_entries(panel, window: int = 20):
    close, high = panel["close"], panel["high"]
    breakout = close > high.rolling(window).max().shift(1)
    exits = close < ind.ema(close, 20)
    return breakout, exits


def golden_cross_entries(panel):
    close = panel["close"]
    e20, e50 = ind.ema(close, 20), ind.ema(close, 50)
    cross_up = (e20 > e50) & (e20.shift(1) <= e50.shift(1))
    cross_down = (e20 < e50) & (e20.shift(1) >= e50.shift(1))
    return cross_up, cross_down


def high52_entries(panel, proximity: float = 0.98):
    close = panel["close"]
    rolling_high = close.rolling(252, min_periods=60).max()
    near_high = close >= proximity * rolling_high
    fresh = near_high & ~near_high.shift(1).fillna(False).astype(bool)
    exits = close < ind.ema(close, 20)
    return fresh, exits


def gap_reversal_entries(panel, gap_pct: float = 3.0):
    close, open_ = panel["close"], panel["open"]
    prev_close = close.shift(1)
    gapped_down = (open_ / prev_close - 1) * 100 < -gap_pct
    recovered = close > open_
    uptrend = close > ind.ema(close, 50)
    exits = ind.rsi(close, 2) > 65
    return gapped_down & recovered & uptrend, exits


def volume_surge_entries(panel, rvol_min: float = 2.0):
    close, volume = panel["close"], panel["volume"]
    rvol = ind.relative_volume(volume)
    surge = (rvol > rvol_min) & (ind.roc(close, 1) > 2) & (close > ind.ema(close, 20))
    exits = close < ind.ema(close, 10)
    return surge, exits


STRATEGIES: dict[str, dict] = {
    "momentum": {
        "name": "Momentum (top-N rebalance)",
        "engine": "rebalance",
        "builder": None,
        "description": "Every few days, buy the N stocks that rose the most recently. Rides winners; the classic quant momentum factor.",
        "best_for": "Trending markets",
    },
    "rsi2": {
        "name": "RSI-2 dip buying",
        "engine": "trades",
        "builder": bt.rsi2_entries,
        "description": "Buy sharp 1-2 day dips (RSI-2 under 10) in stocks that are still in uptrends; sell the bounce.",
        "best_for": "Choppy up-markets",
    },
    "macd": {
        "name": "MACD crossover",
        "engine": "trades",
        "builder": bt.macd_entries,
        "description": "Buy when short-term momentum turns up through its trigger line inside an uptrend; exit on the opposite cross.",
        "best_for": "Swing reversals",
    },
    "bollinger": {
        "name": "Bollinger snapback",
        "engine": "trades",
        "builder": bt.bollinger_entries,
        "description": "Buy when price stretches below its lower Bollinger band in an uptrend and ride the snap back to the middle.",
        "best_for": "Oversold bounces",
    },
    "donchian": {
        "name": "20-day breakout",
        "engine": "trades",
        "builder": donchian_entries,
        "description": "Buy a close above the last 20 days' high — the turtle-trader breakout. Exit when the trend bends (below 20-day EMA).",
        "best_for": "New trends starting",
    },
    "golden": {
        "name": "Golden cross",
        "engine": "trades",
        "builder": golden_cross_entries,
        "description": "Buy when the 20-day average crosses above the 50-day (trend turning up); exit on the reverse cross.",
        "best_for": "Patient trend-following",
    },
    "high52": {
        "name": "52-week high momentum",
        "engine": "trades",
        "builder": high52_entries,
        "description": "Buy stocks breaking to within 2% of their 52-week high — strength begets strength. Exit below the 20-day EMA.",
        "best_for": "Bull markets",
    },
    "gap": {
        "name": "Gap-down reversal",
        "engine": "trades",
        "builder": gap_reversal_entries,
        "description": "Buy uptrend stocks that gap down 3%+ at the open but claw back above the open by the close — panic that faded.",
        "best_for": "Overreactions to news",
    },
    "volume": {
        "name": "Volume surge",
        "engine": "trades",
        "builder": volume_surge_entries,
        "description": "Buy a 2%+ up-day on at least twice normal volume above the 20-day EMA — institutions leaving footprints.",
        "best_for": "Momentum ignition",
    },
}


def registry_meta() -> list[dict]:
    return [
        {"key": k, "name": v["name"], "description": v["description"], "best_for": v["best_for"], "engine": v["engine"]}
        for k, v in STRATEGIES.items()
    ]
