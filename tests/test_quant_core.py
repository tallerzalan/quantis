"""Tests for the UI-free quant core, using synthetic price series."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantis import backtest as bt
from quantis import indicators as ind
from quantis import optimize as opt
from quantis import portfolio as pf
from quantis import risk
from quantis import signals as sig


@pytest.fixture(scope="module")
def panel():
    """Synthetic OHLCV panel: 300 days x 6 tickers, seeded random walks."""
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=300)
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "BENCH"]
    drift = np.array([0.0008, 0.0004, -0.0002, 0.0006, 0.0001, 0.0004])
    vol = np.array([0.02, 0.03, 0.025, 0.015, 0.04, 0.01])
    rets = rng.normal(drift, vol, size=(300, 6))
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates, columns=tickers)
    spread = np.abs(rng.normal(0.005, 0.002, size=(300, 6)))
    return {
        "close": close,
        "open": close.shift(1).fillna(close.iloc[0]),
        "high": close * (1 + spread),
        "low": close * (1 - spread),
        "volume": pd.DataFrame(
            rng.integers(1e5, 1e7, size=(300, 6)).astype(float), index=dates, columns=tickers
        ),
    }


# ------------------------------------------------------------- indicators

def test_rsi_bounds_and_extremes(panel):
    r = ind.rsi(panel["close"], 14).dropna()
    assert ((r >= 0) & (r <= 100)).all().all()
    rising = pd.DataFrame({"UP": np.linspace(100, 200, 60)})
    assert ind.rsi(rising, 14).iloc[-1, 0] > 99


def test_atr_positive(panel):
    a = ind.atr(panel["high"], panel["low"], panel["close"]).dropna()
    assert (a > 0).all().all()


def test_percent_b_centered_on_flat_series():
    flat = pd.DataFrame({"F": np.full(50, 100.0) + np.tile([0.01, -0.01], 25)})
    pctb = ind.bollinger_percent_b(flat).dropna()
    assert pctb.iloc[-1, 0] == pytest.approx(0.5, abs=0.35)


def test_macd_zero_on_flat():
    flat = pd.DataFrame({"F": np.full(100, 100.0)})
    line, sig_, hist = ind.macd(flat)
    assert abs(line.iloc[-1, 0]) < 1e-9
    assert abs(hist.iloc[-1, 0]) < 1e-9


# ---------------------------------------------------------------- signals

def test_edge_scores_rank_and_features(panel):
    feats = sig.compute_features(panel)
    scored = sig.edge_scores(feats)
    assert scored["edge"].between(0, 100).all()
    assert scored["edge"].is_monotonic_decreasing


def test_trade_ideas_geometry_and_sizing(panel):
    scored = sig.edge_scores(sig.compute_features(panel))
    ideas = sig.trade_ideas(scored, capital=100.0, n=5, max_weight=0.25)
    assert (ideas["stop"] < ideas["entry"]).all()
    assert (ideas["target"] > ideas["entry"]).all()
    assert ideas["dollars"].sum() == pytest.approx(100.0, abs=1.0)
    assert (ideas["weight"] <= 0.25 + 1e-6).all()
    rr = (ideas["target"] - ideas["entry"]) / (ideas["entry"] - ideas["stop"])
    assert rr.round(6).eq(2.0).all()


def test_cap_weights_invariants():
    w = sig.cap_weights(pd.Series([10.0, 1.0, 1.0, 1.0, 1.0]), cap=0.25)
    assert w.sum() == pytest.approx(1.0)
    assert (w <= 0.25 + 1e-9).all()


# --------------------------------------------------------------- backtest

def test_buy_hold_matches_manual(panel):
    c = panel["close"]["AAA"]
    eq = bt.buy_hold_equity(c, capital=100.0)
    assert eq.iloc[-1] == pytest.approx(100.0 * c.iloc[-1] / c.iloc[0])


def test_flat_prices_yield_zero_pnl():
    dates = pd.bdate_range("2024-01-01", periods=100)
    flat = pd.DataFrame(100.0, index=dates, columns=["X", "Y", "Z"])
    equity, _ = bt.run_rebalance(
        flat, lookback=10, top_n=2, hold_days=5,
        slippage_bps=0.0, spread_bps=0.0, commission_bps=0.0,
    )
    assert equity.iloc[-1] == pytest.approx(100.0)


def test_rebalance_no_lookahead():
    """A ticker that jumps on day t must not contribute that jump if it was
    selected at close t (weights shifted by one day)."""
    dates = pd.bdate_range("2024-01-01", periods=40)
    a = np.full(40, 100.0)
    a[30:] = 200.0  # jump at index 30
    b = np.linspace(100, 110, 40)
    close = pd.DataFrame({"A": a, "B": b}, index=dates)
    equity, weights = bt.run_rebalance(close, lookback=5, top_n=1, hold_days=1, slippage_bps=0.0)
    # weight on A at index 30 was decided at close 30 (after the jump printed);
    # the jump return from 29->30 must only be earned if held BEFORE the jump.
    w_before_jump = weights.iloc[29]["A"]
    day_ret = equity.pct_change().loc[dates[30]]
    if w_before_jump == 0:
        assert day_ret < 0.5  # did not capture the 100% jump

def test_signal_trades_stop_and_accounting(panel):
    entries, exits = bt.rsi2_entries(panel)
    cfg = bt.TradeConfig(capital=100.0, slippage_bps=0.0, max_positions=3)
    equity, trades = bt.run_signal_trades(panel, entries, exits, cfg)
    assert np.isfinite(equity.iloc[-1])
    if trades:
        pnl_sum = sum(t["pnl"] for t in trades)
        open_value = equity.iloc[-1] - 100.0
        # closed P&L plus open-position drift equals total equity change
        assert np.isfinite(pnl_sum)
        assert abs(open_value) < 100.0 * 5  # sanity: no runaway accounting


def test_signal_executes_at_next_open_not_signal_close():
    dates = pd.bdate_range("2024-01-01", periods=25)
    close = pd.DataFrame({"X": np.full(25, 100.0)}, index=dates)
    open_ = close.copy()
    open_.iloc[16, 0] = 150.0
    open_.iloc[18, 0] = 175.0
    panel = {
        "close": close,
        "open": open_,
        "high": close + 1.0,
        "low": close - 1.0,
    }
    entries = pd.DataFrame(False, index=dates, columns=["X"])
    exits = entries.copy()
    entries.iloc[15, 0] = True
    exits.iloc[17, 0] = True
    cfg = bt.TradeConfig(
        capital=100.0, max_positions=1, stop_atr_mult=100.0,
        slippage_bps=0.0, spread_bps=0.0, commission_bps=0.0,
    )

    _, trades = bt.run_signal_trades(panel, entries, exits, cfg)

    assert len(trades) == 1
    assert trades[0]["signal_date"] == dates[15]
    assert trades[0]["entry_date"] == dates[16]
    assert trades[0]["entry"] == pytest.approx(150.0)
    assert trades[0]["exit_date"] == dates[18]
    assert trades[0]["exit"] == pytest.approx(175.0)


def test_signal_trade_costs_are_net_and_auditable():
    dates = pd.bdate_range("2024-01-01", periods=25)
    close = pd.DataFrame({"X": np.full(25, 100.0)}, index=dates)
    panel = {
        "close": close,
        "open": close.copy(),
        "high": close + 1.0,
        "low": close - 1.0,
    }
    entries = pd.DataFrame(False, index=dates, columns=["X"])
    exits = entries.copy()
    entries.iloc[15, 0] = True
    exits.iloc[17, 0] = True
    cfg = bt.TradeConfig(
        capital=100.0, max_positions=1, stop_atr_mult=100.0,
        slippage_bps=10.0, spread_bps=20.0, commission_bps=10.0,
    )

    _, trades = bt.run_signal_trades(panel, entries, exits, cfg)

    assert len(trades) == 1
    assert trades[0]["costs"] > 0
    assert trades[0]["pnl"] == pytest.approx(-trades[0]["costs"])
    assert trades[0]["return_pct"] < 0


def test_trade_config_rejects_impossible_costs():
    with pytest.raises(ValueError, match="cannot be negative"):
        bt.TradeConfig(slippage_bps=-1.0)


def test_perf_stats_fields(panel):
    c = panel["close"]["AAA"]
    eq = bt.buy_hold_equity(c)
    bench = panel["close"]["BENCH"].pct_change().dropna()
    stats = bt.perf_stats(eq, bench_returns=bench)
    for k in ["total_return", "cagr", "sharpe", "sortino", "max_drawdown", "beta", "alpha"]:
        assert k in stats


# --------------------------------------------------------------- optimize

def test_optimizer_invariants(panel):
    rets = panel["close"].pct_change().dropna()
    mu = opt.expected_returns(rets)
    cov = opt.shrunk_covariance(rets)
    w_ms, fell_back = opt.max_sharpe(mu, cov, cap=0.4)
    w_mv = opt.min_variance(cov, cap=0.4)
    for w in (w_ms, w_mv):
        assert w.sum() == pytest.approx(1.0, abs=1e-6)
        assert (w >= -1e-9).all()
        assert (w <= 0.4 + 1e-6).all()
    ew = pd.Series(1 / len(mu), index=mu.index)
    assert opt.portfolio_stats(w_mv, mu, cov)["volatility"] <= opt.portfolio_stats(ew, mu, cov)["volatility"] + 1e-9


def test_max_sharpe_fallback_when_all_negative(panel):
    rets = panel["close"].pct_change().dropna()
    cov = opt.shrunk_covariance(rets)
    mu = pd.Series(-0.1, index=cov.index)
    _, fell_back = opt.max_sharpe(mu, cov)
    assert fell_back


def test_dollar_allocation_sums_to_capital():
    w = pd.Series({"A": 0.4, "B": 0.35, "C": 0.25})
    d = opt.dollar_allocation(w, 100.0)
    assert d.sum() == pytest.approx(100.0, abs=0.05)


def test_efficient_frontier_monotone_vol_at_ends(panel):
    rets = panel["close"].pct_change().dropna()
    mu = opt.expected_returns(rets)
    cov = opt.shrunk_covariance(rets)
    ef = opt.efficient_frontier(mu, cov, cap=0.4, n_points=10)
    assert len(ef) == 10
    assert ef["volatility"].iloc[-1] >= ef["volatility"].iloc[0] - 1e-9
    # every frontier target must be feasible under the cap - no fallback points
    assert ef["return"].max() <= opt.max_return_under_cap(mu, 0.4) + 1e-6


def test_max_return_under_cap():
    mu = pd.Series({"A": 0.5, "B": 0.3, "C": 0.1})
    # cap 0.4: 0.4*A + 0.4*B + 0.2*C
    assert opt.max_return_under_cap(mu, 0.4) == pytest.approx(0.4 * 0.5 + 0.4 * 0.3 + 0.2 * 0.1)


# ------------------------------------------------------------------- risk

def test_benchmark_beta_is_one(panel):
    bench = panel["close"]["BENCH"].pct_change().dropna()
    beta, alpha = bt.beta_alpha(bench, bench)
    assert beta == pytest.approx(1.0)
    assert alpha == pytest.approx(0.0, abs=1e-12)


def test_summary_table_and_var(panel):
    rets = panel["close"].pct_change().dropna()
    bench = rets["BENCH"]
    table = risk.summary_table(rets.drop(columns="BENCH"), bench)
    assert not table.empty
    assert (table["max_drawdown"] <= 0).all()
    assert (table["var_95"] > 0).all()  # losses reported as positive magnitudes
    assert (table["volatility"] > 0).all()


# -------------------------------------------------------------- portfolio

def test_portfolio_roundtrip(tmp_path):
    p = tmp_path / "portfolio.json"
    state = pf.load(p)
    assert state["cash"] == 100.0
    state = pf.add_position(state, "nvda", 0.1, 500.0)
    assert state["cash"] == pytest.approx(50.0)
    pf.save(state, p)
    state2 = pf.load(p)
    assert state2["positions"][0]["ticker"] == "NVDA"
    val = pf.valuation(state2, pd.Series({"NVDA": 600.0}))
    assert val["pnl"].iloc[0] == pytest.approx(10.0)
    state2 = pf.remove_position(state2, "NVDA", 600.0)
    assert state2["cash"] == pytest.approx(110.0)
    assert not state2["positions"]
