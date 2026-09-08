"""Run user-written strategy code against the backtest engine.

The user defines, in Python:

    def strategy(data, ind):
        close = data["close"]
        entries = ind.rsi(close, 14) < 30
        exits   = ind.rsi(close, 14) > 60
        return entries, exits

`data` is the OHLCV panel (dict of DataFrames: open/high/low/close/volume,
dates x tickers); `ind` is the quantis.indicators module; pd/np are available.
Returns boolean DataFrames aligned to `data["close"]`.

This executes the user's own code on their own machine (the app is local,
single-user). Builtins are trimmed to keep honest mistakes contained, not to
resist a determined attacker.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import indicators as ind

_SAFE_BUILTINS = {
    n: __builtins__[n] if isinstance(__builtins__, dict) else getattr(__builtins__, n)
    for n in (
        "abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "len",
        "list", "max", "min", "print", "range", "round", "sum", "tuple", "zip",
        "sorted", "reversed", "map", "filter", "set", "str", "isinstance", "Exception",
    )
}

TEMPLATE = '''def strategy(data, ind):
    """Buy when 14-day RSI is oversold, sell when it recovers.

    data: dict of DataFrames (open/high/low/close/volume), dates x tickers
    ind:  indicators - ind.rsi, ind.ema, ind.macd, ind.atr, ind.roc,
          ind.bollinger_percent_b, ind.adx, ind.relative_volume
    Return (entries, exits): True where you'd buy / sell at that day's close.
    """
    close = data["close"]
    rsi = ind.rsi(close, 14)
    uptrend = close > ind.ema(close, 50)

    entries = (rsi < 30) & uptrend
    exits = rsi > 60
    return entries, exits
'''

EXAMPLES = {
    "Oversold RSI (template)": TEMPLATE,
    "Price vs moving average": '''def strategy(data, ind):
    close = data["close"]
    e10, e30 = ind.ema(close, 10), ind.ema(close, 30)
    entries = (e10 > e30) & (e10.shift(1) <= e30.shift(1))
    exits = (e10 < e30) & (e10.shift(1) >= e30.shift(1))
    return entries, exits
''',
    "Big down day snapback": '''def strategy(data, ind):
    close = data["close"]
    one_day = ind.roc(close, 1)          # yesterday-to-today %
    uptrend = close > ind.ema(close, 50)
    entries = (one_day < -4) & uptrend   # 4%+ drop inside an uptrend
    exits = ind.rsi(close, 2) > 70       # sold once bounce is stretched
    return entries, exits
''',
}


class StrategyError(Exception):
    pass


def run_user_strategy(code: str, panel: dict[str, pd.DataFrame]):
    """Compile + execute user code, validate its output, return (entries, exits)."""
    if "import" in code:
        raise StrategyError("Imports aren't needed — pd, np and ind are already available.")
    ns: dict = {"__builtins__": _SAFE_BUILTINS, "pd": pd, "np": np, "ind": ind}
    try:
        exec(compile(code, "<your strategy>", "exec"), ns)
    except SyntaxError as e:
        raise StrategyError(f"Syntax error on line {e.lineno}: {e.msg}") from e
    fn = ns.get("strategy")
    if not callable(fn):
        raise StrategyError("Define a function called `strategy(data, ind)`.")
    try:
        out = fn(panel, ind)
    except Exception as e:
        raise StrategyError(f"Your strategy crashed: {type(e).__name__}: {e}") from e
    if not (isinstance(out, tuple) and len(out) == 2):
        raise StrategyError("Return two things: (entries, exits).")
    entries, exits = out
    close = panel["close"]
    for name, df in (("entries", entries), ("exits", exits)):
        if not isinstance(df, pd.DataFrame):
            raise StrategyError(f"{name} must be a DataFrame of True/False (dates x tickers).")
    entries = entries.reindex(index=close.index, columns=close.columns).fillna(False).astype(bool)
    exits = exits.reindex(index=close.index, columns=close.columns).fillna(False).astype(bool)
    if not entries.any().any():
        raise StrategyError("Your entry rule never fired on this data — loosen the conditions.")
    return entries, exits
