"""Tests for the new quant capabilities: factors, extra risk metrics,
new indicators, and Black-Litterman."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantis import factors as fac
from quantis import indicators as ind
from quantis import optimize as opt
from quantis import risk


@pytest.fixture(scope="module")
def synth():
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2023-01-01", periods=400)
    tickers = ["AAA", "BBB", "CCC", "SPY"]
    rets = rng.normal([0.0007, 0.0003, 0.0009, 0.0004], [0.02, 0.03, 0.018, 0.01], (400, 4))
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, 0)), index=dates, columns=tickers)
    return {"close": close, "dates": dates, "rng": rng}


# ---------------------------------------------------------------- factors

def test_factor_returns_columns():
    dates = pd.bdate_range("2023-01-01", periods=200)
    rng = np.random.default_rng(1)
    etfs = fac.FACTOR_TICKERS
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, (200, len(etfs))), 0)),
                         index=dates, columns=etfs)
    fr = fac.factor_returns(close)
    assert set(fr.columns) == set(fac.FACTOR_PROXIES.keys())
    assert not fr.empty


def test_factor_exposures_recovers_betas():
    dates = pd.bdate_range("2023-01-01", periods=300)
    rng = np.random.default_rng(2)
    facs = pd.DataFrame({
        "market": rng.normal(0, 0.01, 300),
        "value": rng.normal(0, 0.008, 300),
        "momentum": rng.normal(0, 0.007, 300),
    }, index=dates)
    y = 1.2 * facs["market"] + 0.4 * facs["value"] + rng.normal(0, 0.001, 300)
    exp = fac.factor_exposures(pd.Series(y, index=dates), facs)
    assert exp["betas"]["market"] == pytest.approx(1.2, abs=0.1)
    assert exp["betas"]["value"] == pytest.approx(0.4, abs=0.1)
    assert 0.9 < exp["r2"] <= 1.0


def test_sector_allocation_and_concentration():
    alloc = fac.sector_allocation({"A": 0.5, "B": 0.3, "C": 0.2},
                                  {"A": "Tech", "B": "Tech", "C": "Energy"})
    assert alloc[0]["sector"] == "Tech"
    assert sum(a["weight"] for a in alloc) == pytest.approx(1.0, abs=1e-6)
    hhi = fac.concentration({"A": 0.5, "B": 0.5})
    assert hhi == pytest.approx(0.5, abs=1e-9)


# ------------------------------------------------------------------- risk

def test_cvar_worse_than_var(synth):
    r = synth["close"]["BBB"].pct_change().dropna()
    assert risk.cvar(r) >= risk.hist_var(r)


def test_cornish_fisher_and_downside_beta(synth):
    r = synth["close"]["AAA"].pct_change().dropna()
    b = synth["close"]["SPY"].pct_change().dropna()
    assert np.isfinite(risk.cornish_fisher_var(r))
    assert np.isfinite(risk.downside_beta(r, b))


def test_rolling_beta_and_ratios(synth):
    r = synth["close"]["AAA"].pct_change().dropna()
    b = synth["close"]["SPY"].pct_change().dropna()
    rb = risk.rolling_beta(r, b)
    assert len(rb) > 0 and rb.notna().all()
    assert np.isfinite(risk.calmar_ratio(r))
    assert risk.omega_ratio(r) > 0


# ------------------------------------------------------------- indicators

def test_new_indicators(synth):
    c, h, l = synth["close"], synth["close"] * 1.01, synth["close"] * 0.99
    v = pd.DataFrame(1e6, index=c.index, columns=c.columns)
    vw = ind.vwap(h, l, c, v).dropna()
    assert (vw > 0).all().all()
    k, d = ind.stochastic(h, l, c)
    kk = k.dropna()
    assert ((kk >= -1e-9) & (kk <= 100 + 1e-9)).all().all()
    mid, up, lo = ind.keltner_channels(h, l, c)
    m = pd.concat([mid, up, lo], axis=1).dropna()
    assert (up.dropna() >= mid.dropna()).all().all()
    assert (mid.dropna() >= lo.dropna()).all().all()
    stop = ind.atr_trailing_stop(h, l, c).dropna()
    assert (stop.diff().dropna() >= -1e-9).all().all()  # never loosens
    ten, kij, sa, sb = ind.ichimoku(h, l, c)
    assert ten.dropna().shape[0] > 0


# -------------------------------------------------------- black-litterman

def test_black_litterman_prior_when_views_equal_equilibrium():
    rng = np.random.default_rng(3)
    a = rng.normal(0, 0.01, (250, 3))
    rets = pd.DataFrame(a, columns=["X", "Y", "Z"])
    cov = opt.shrunk_covariance(rets)
    w_mkt = pd.Series(1 / 3, index=cov.index)
    pi = opt.implied_returns(cov, w_mkt, delta=2.5)
    mu_bl = opt.black_litterman(cov, w_mkt, views=pi, delta=2.5)
    assert np.allclose(mu_bl.values, pi.values, atol=1e-6)


def test_black_litterman_shifts_toward_views():
    rng = np.random.default_rng(4)
    rets = pd.DataFrame(rng.normal(0, 0.01, (250, 3)), columns=["X", "Y", "Z"])
    cov = opt.shrunk_covariance(rets)
    w_mkt = pd.Series(1 / 3, index=cov.index)
    pi = opt.implied_returns(cov, w_mkt, delta=2.5)
    bullish = pi.copy()
    bullish["X"] += 0.20  # strong view that X outperforms
    mu_bl = opt.black_litterman(cov, w_mkt, views=bullish, delta=2.5, view_confidence=2.0)
    assert mu_bl["X"] > pi["X"]
