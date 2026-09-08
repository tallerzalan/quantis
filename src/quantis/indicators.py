"""Vectorized technical indicators. All functions accept a DataFrame
(dates x tickers) and return one of the same shape unless noted."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(close: pd.DataFrame, span: int) -> pd.DataFrame:
    return close.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Wilder's RSI, bounded [0, 100]."""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    # all-gain windows: avg_loss == 0 -> RSI 100 (unless avg_gain also 0 -> neutral 50)
    out = out.where(avg_loss != 0, np.where(avg_gain > 0, 100.0, 50.0))
    return out


def macd(close: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram)."""
    line = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = line.ewm(span=signal, adjust=False).mean()
    return line, sig, line - sig


def true_range(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame) -> pd.DataFrame:
    prev_close = close.shift(1)
    a = high - low
    b = (high - prev_close).abs()
    c = (low - prev_close).abs()
    return pd.concat([a, b, c], keys=["a", "b", "c"]).groupby(level=1).max().reindex(a.index)


def atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    tr = true_range(high, low, close)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def bollinger_percent_b(close: pd.DataFrame, window: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    mid = close.rolling(window).mean()
    sd = close.rolling(window).std()
    upper = mid + num_std * sd
    lower = mid - num_std * sd
    return (close - lower) / (upper - lower)


def roc(close: pd.DataFrame, n: int) -> pd.DataFrame:
    """Rate of change over n bars, in percent."""
    return close.pct_change(n) * 100


def adx(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    up = high.diff()
    down = -low.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = true_range(high, low, close)
    atr_ = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr_
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    return dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def relative_volume(volume: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    return volume / volume.rolling(window).mean()


def vwap(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
         volume: pd.DataFrame, window: int = 20) -> pd.DataFrame:
    """Rolling volume-weighted average price - the average price actually paid,
    weighted by how much traded there. A common institutional fair-value anchor."""
    typical = (high + low + close) / 3
    pv = (typical * volume).rolling(window).sum()
    vol = volume.rolling(window).sum().replace(0.0, np.nan)
    return pv / vol


def stochastic(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
               k: int = 14, d: int = 3):
    """Stochastic oscillator. Returns (%K, %D) bounded [0, 100]; >80 overbought,
    <20 oversold - where price sits within its recent range."""
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    percent_k = 100 * (close - ll) / (hh - ll).replace(0.0, np.nan)
    return percent_k, percent_k.rolling(d).mean()


def obv(close: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """On-balance volume: a running total that adds volume on up days and
    subtracts it on down days - a proxy for accumulation vs distribution."""
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def keltner_channels(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
                     window: int = 20, mult: float = 2.0, atr_period: int = 10):
    """Returns (middle, upper, lower): an EMA envelope band-width by ATR.
    Steadier than Bollinger Bands because it uses true range, not close std."""
    mid = ema(close, window)
    rng = atr(high, low, close, atr_period)
    return mid, mid + mult * rng, mid - mult * rng


def atr_trailing_stop(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
                      period: int = 14, mult: float = 3.0) -> pd.DataFrame:
    """A long-side trailing stop that ratchets up: the running max of
    (close - mult*ATR), so it never loosens while a trade works."""
    stop = close - mult * atr(high, low, close, period)
    return stop.cummax()


def ichimoku(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
             conversion: int = 9, base: int = 26, span_b: int = 52):
    """Ichimoku core lines (no forward displacement, for alignment with price):
    returns (tenkan, kijun, senkou_a, senkou_b). Price above both spans = the
    'cloud' is bullish support beneath it."""
    def midline(n):
        return (high.rolling(n).max() + low.rolling(n).min()) / 2
    tenkan = midline(conversion)
    kijun = midline(base)
    senkou_a = (tenkan + kijun) / 2
    senkou_b = midline(span_b)
    return tenkan, kijun, senkou_a, senkou_b
