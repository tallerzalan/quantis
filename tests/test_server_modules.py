"""Tests for interpret, custom strategy execution, strategy registry, watchlist."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantis import backtest as bt
from quantis import custom as cst
from quantis import interpret as itp
from quantis import strategies as strat
from quantis import watchlist as wl


@pytest.fixture(scope="module")
def panel():
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2024-01-01", periods=300)
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    rets = rng.normal(0.0005, 0.02, size=(300, 4))
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    spread = np.abs(rng.normal(0.005, 0.002, size=(300, 4)))
    return {
        "close": close,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * (1 + spread),
        "low": close * (1 - spread),
        "volume": pd.DataFrame(rng.integers(1e5, 1e7, size=(300, 4)).astype(float), index=dates, columns=tickers),
    }


# -------------------------------------------------------------- interpret

def test_verdict_levels_span_scale():
    assert itp.sharpe_verdict(2.0)["level"] == "great"
    assert itp.sharpe_verdict(-0.5)["level"] == "bad"
    assert itp.beta_verdict(3.0)["level"] == "bad"
    assert itp.beta_verdict(0.3)["level"] == "good"
    assert itp.alpha_verdict(0.15)["level"] == "great"
    assert itp.drawdown_verdict(-0.05)["level"] == "great"
    assert itp.drawdown_verdict(-0.5)["level"] == "bad"
    for v in (itp.sharpe_verdict(np.nan), itp.beta_verdict(None)):
        assert v["level"] == "ok"


def test_backtest_summary_shape():
    stats = {"total_return": 0.14, "sharpe": 1.1, "alpha": 0.03, "beta": 0.9,
             "max_drawdown": -0.12, "win_rate": 0.6, "profit_factor": 1.5}
    s = itp.backtest_summary(stats, 100.0, 0.10)
    assert s["grade"] in {"A+", "A", "B+", "B", "C+", "C", "D", "D-", "F"}
    assert "$100" in s["narrative"] or "$114" in s["narrative"]
    assert set(s["verdicts"]) == {"sharpe", "alpha", "beta", "drawdown", "profit_factor"}


def test_regime_branches():
    assert itp.regime(True, 0.7)["label"] == "Risk-on"
    assert itp.regime(False, 0.2)["label"] == "Risk-off"
    assert itp.regime(True, 0.3)["label"] == "Mixed"


# ----------------------------------------------------------------- custom

ALWAYS_FIRES = (
    "def strategy(data, ind):\n"
    "    close = data['close']\n"
    "    entries = ind.roc(close, 1) < 0\n"
    "    exits = ind.roc(close, 1) > 0\n"
    "    return entries, exits\n"
)


def test_custom_strategy_runs(panel):
    entries, exits = cst.run_user_strategy(ALWAYS_FIRES, panel)
    assert entries.dtypes.eq(bool).all() and exits.dtypes.eq(bool).all()
    assert entries.shape == panel["close"].shape
    equity, trades = bt.run_signal_trades(panel, entries, exits, bt.TradeConfig())
    assert np.isfinite(equity.iloc[-1])


def test_custom_strategy_error_paths(panel):
    with pytest.raises(cst.StrategyError, match="Syntax"):
        cst.run_user_strategy("def strategy(data, ind:\n  pass", panel)
    with pytest.raises(cst.StrategyError, match="strategy"):
        cst.run_user_strategy("x = 1", panel)
    with pytest.raises(cst.StrategyError, match="Imports"):
        cst.run_user_strategy("import os\ndef strategy(d, i): ...", panel)
    with pytest.raises(cst.StrategyError, match="never fired"):
        cst.run_user_strategy(
            "def strategy(data, ind):\n"
            "    c = data['close']\n"
            "    return c > c.max().max() * 2, c < 0\n",
            panel,
        )
    with pytest.raises(cst.StrategyError, match="crashed"):
        cst.run_user_strategy("def strategy(data, ind):\n    return data['nope'], None\n", panel)


def test_all_examples_are_valid(panel):
    for name, code in cst.EXAMPLES.items():
        try:
            entries, exits = cst.run_user_strategy(code, panel)
            assert entries.shape == panel["close"].shape, name
        except cst.StrategyError as e:
            if "never fired" not in str(e):  # random walk may not trip every rule
                raise


# ------------------------------------------------------------- strategies

def test_registry_builders_run(panel):
    for key, meta in strat.STRATEGIES.items():
        if meta["engine"] != "trades":
            continue
        entries, exits = meta["builder"](panel)
        assert entries.shape == panel["close"].shape, key
        equity, _ = bt.run_signal_trades(panel, entries, exits, bt.TradeConfig())
        assert np.isfinite(equity.iloc[-1]), key


def test_registry_meta_complete():
    meta = strat.registry_meta()
    assert len(meta) == len(strat.STRATEGIES)
    for m in meta:
        assert m["name"] and m["description"] and m["best_for"]


# -------------------------------------------------------------- watchlist

def test_watchlist_roundtrip(tmp_path):
    p = tmp_path / "watchlist.json"
    base = wl.load(p)
    assert "SPY" in base  # defaults to curated universe
    wl.save(["AAPL", "MSFT"], p)
    assert wl.load(p) == ["AAPL", "MSFT"]
    assert "TSLA" in wl.add("tsla", p)
    assert "TSLA" not in wl.remove("TSLA", p)
    assert len(wl.reset(p)) == len(base)
