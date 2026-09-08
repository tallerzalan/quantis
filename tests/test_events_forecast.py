"""Tests for significant-move detection, attribution, and Monte Carlo —
synthetic series only, no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from quantis import events as evt
from quantis import interpret as itp
from quantis import montecarlo as mc

DATES = pd.bdate_range("2025-01-01", periods=300)


@pytest.fixture(scope="module")
def jumpy():
    """~1%-vol random walk with a +12% jump injected on a known date."""
    rng = np.random.default_rng(7)
    rets = rng.normal(0.0003, 0.01, size=300)
    jump_i = 200
    rets[jump_i] = 0.12
    close = pd.Series(100 * np.cumprod(1 + rets), index=DATES, name="close")
    volume = pd.Series(1e6, index=DATES)
    volume.iloc[jump_i] = 5e6
    return close, volume, DATES[jump_i]


# ---------------------------------------------------------------- detection

def test_jump_detected_and_stats_sane(jumpy):
    close, volume, jump_date = jumpy
    ev = evt.move_significance(close, volume)
    assert jump_date in ev.index
    row = ev.loc[jump_date]
    assert row["z"] > 4
    assert 0 < row["pvalue"] < 0.001
    assert row["rvol"] > 3
    assert ev["z"].abs().idxmax() == jump_date
    assert len(ev) < 15  # noise days shouldn't flood the list


def test_spike_does_not_mask_itself(jumpy):
    """Sigma is lagged one day, so the jump can't dampen its own z-score."""
    close, volume, jump_date = jumpy
    ev = evt.move_significance(close, volume)
    assert abs(ev.loc[jump_date, "ret"] - 0.12) < 0.001


def test_no_events_below_threshold():
    steady = pd.Series(100 * np.cumprod(1 + np.full(100, 0.001)), index=DATES[:100])
    assert evt.move_significance(steady).empty


# -------------------------------------------------------------- attribution

def test_earnings_attribution_same_or_prior_day(jumpy):
    close, volume, jump_date = jumpy
    ev = evt.move_significance(close, volume)
    prior_session = DATES[DATES.get_loc(jump_date) - 1]
    for edate in (jump_date, prior_session):
        out = evt.attribute_events(ev.loc[[jump_date]], close.index, earnings=[edate])
        assert out[0]["catalyst"] == "earnings"


def test_market_vs_stock_specific(jumpy):
    close, volume, jump_date = jumpy
    ev = evt.move_significance(close, volume).loc[[jump_date]]
    flat_bench = pd.Series(500.0 + np.arange(300) * 0.1, index=DATES)
    out = evt.attribute_events(ev, close.index, bench_close=flat_bench)
    assert out[0]["market_move"] is False
    assert out[0]["catalyst"] == "unknown"

    co_moving = close * 5  # same returns -> same z on the jump day
    out = evt.attribute_events(ev, close.index, bench_close=co_moving)
    assert out[0]["market_move"] is True
    assert out[0]["catalyst"] == "market"


def test_news_attribution_and_priority(jumpy):
    close, volume, jump_date = jumpy
    ev = evt.move_significance(close, volume).loc[[jump_date]]
    news = [{"when": jump_date + pd.Timedelta(hours=9), "title": "Blowout quarter", "publisher": "X", "url": None}]
    out = evt.attribute_events(ev, close.index, news=news)
    assert out[0]["catalyst"] == "news"
    assert out[0]["headlines"][0]["title"] == "Blowout quarter"
    # earnings outranks news
    out = evt.attribute_events(ev, close.index, earnings=[jump_date], news=news)
    assert out[0]["catalyst"] == "earnings"
    assert out[0]["headlines"]  # headlines still attached


def test_event_story_reads_sane(jumpy):
    close, volume, jump_date = jumpy
    ev = evt.move_significance(close, volume).loc[[jump_date]]
    out = evt.attribute_events(ev, close.index, earnings=[jump_date])
    story = itp.event_story(out[0], "TEST")
    assert "TEST jumped +12.0%" in story["story"]
    assert story["catalyst_label"] == "Earnings report"
    assert "σ" in story["title"]


def test_odds_phrase_ranges():
    assert "1 trading day in" in itp.odds_phrase(0.05)
    assert "years" in itp.odds_phrase(1e-4)
    assert "never" in itp.odds_phrase(0.0)
    assert "news, not noise" in itp.odds_phrase(1e-12)  # 8σ+ days: no silly numbers


# -------------------------------------------------------------- monte carlo

@pytest.fixture(scope="module")
def up_returns():
    rng = np.random.default_rng(3)
    return pd.Series(rng.normal(0.004, 0.01, size=250))


def test_paths_shape_and_seed(up_returns):
    p1 = mc.simulate_paths(up_returns, horizon=21, n_paths=500, seed=11)
    p2 = mc.simulate_paths(up_returns, horizon=21, n_paths=500, seed=11)
    assert p1.shape == (500, 22)
    assert (p1[:, 0] == 1.0).all()
    assert np.array_equal(p1, p2)
    p3 = mc.simulate_paths(up_returns, horizon=21, n_paths=500, seed=12)
    assert not np.array_equal(p1, p3)


def test_drift_direction(up_returns):
    up = mc.simulate_paths(up_returns, n_paths=1000, seed=1)
    assert mc.summarize(up)["prob_up"] > 0.7
    down = mc.simulate_paths(-up_returns, n_paths=1000, seed=1)
    assert mc.summarize(down)["prob_up"] < 0.3


def test_fan_bands_monotone(up_returns):
    paths = mc.simulate_paths(up_returns, n_paths=800, seed=5)
    fan = mc.fan_bands(paths, last_price=50.0)
    assert (fan["p05"] <= fan["p25"]).all()
    assert (fan["p25"] <= fan["p50"]).all()
    assert (fan["p50"] <= fan["p75"]).all()
    assert (fan["p75"] <= fan["p95"]).all()
    assert fan.iloc[0]["p50"] == pytest.approx(50.0)


def test_dip_probabilities_monotone(up_returns):
    paths = mc.simulate_paths(up_returns, n_paths=800, seed=5)
    probs = mc.dip_probabilities(paths, [0.01, 0.03, 0.08])
    assert probs[0.01] >= probs[0.03] >= probs[0.08]


def test_best_entry_on_crafted_paths():
    # every path bottoms exactly at session 3 at 0.9
    path = np.array([1.0, 0.95, 0.92, 0.90, 0.96, 1.05])
    paths = np.tile(path, (10, 1))
    best = mc.best_entry(paths)
    assert best["median_day"] == 3
    assert best["median_low"] == pytest.approx(0.90)
    assert best["day_hist"][2] == 10  # session 3 -> index 2


def test_dip_buy_accounting():
    # A: dips 6% then rallies through +15% target (from the 0.94 entry)
    a = np.array([1.0, 0.94, 1.00, 1.10, 1.16, 1.16])
    # B: dips 6% then collapses through the 7% stop
    b = np.array([1.0, 0.94, 0.90, 0.85, 0.80, 0.80])
    # C: never dips -> never filled
    c = np.array([1.0, 1.02, 1.05, 1.08, 1.10, 1.12])
    paths = np.stack([a, b, c])
    out = mc.dip_buy_outcomes(paths, dip=0.05, target=0.15, stop=0.07)
    assert out["fill_rate"] == pytest.approx(2 / 3)
    assert out["win_rate"] == pytest.approx(0.5)
    assert out["avg_ret_filled"] == pytest.approx((0.15 - 0.07) / 2)
    assert out["avg_ret_overall"] == pytest.approx((0.15 - 0.07) / 3)
    assert out["median_days_to_fill"] == pytest.approx(1.0)
    # buy-today comparison: A hits +15%, B stops at -7%, C times out at +12%
    assert out["buy_now"]["avg_ret"] == pytest.approx((0.15 - 0.07 + 0.12) / 3)
    assert out["buy_now"]["win_rate"] == pytest.approx(2 / 3)


def test_entry_verdict_levels():
    buy = itp.entry_verdict({"rsi14": 28, "pctb": 0.1, "off_high": -0.09, "above_ema50": True, "earnings_in": None})
    assert buy["level"] == "good"
    knife = itp.entry_verdict({"rsi14": 28, "pctb": 0.1, "off_high": -0.2, "above_ema50": False, "earnings_in": None})
    assert knife["level"] == "weak"
    chase = itp.entry_verdict({"rsi14": 80, "pctb": 0.97, "off_high": -0.001, "above_ema50": True, "earnings_in": 5})
    assert chase["level"] == "weak"
    assert chase.get("earnings_warning")
    mid = itp.entry_verdict({"rsi14": 50, "pctb": 0.5, "off_high": -0.03, "above_ema50": True, "earnings_in": None})
    assert mid["level"] == "ok"


def test_vol_scaled_paths_track_current_regime():
    rng = np.random.default_rng(9)
    wild_then_calm = pd.Series(np.concatenate([
        rng.normal(0, 0.03, 200),   # wild past
        rng.normal(0, 0.005, 50),   # calm now
    ]))
    hist = mc.simulate_paths(wild_then_calm, n_paths=1500, seed=4, vol_mode="history")
    cur = mc.simulate_paths(wild_then_calm, n_paths=1500, seed=4, vol_mode="current")
    # day-1 dispersion should reflect today's calm, not the wild average
    assert cur[:, 1].std() < 0.5 * hist[:, 1].std()

    calm_then_wild = pd.Series(np.concatenate([
        rng.normal(0, 0.005, 200),
        rng.normal(0, 0.03, 50),
    ]))
    hist2 = mc.simulate_paths(calm_then_wild, n_paths=1500, seed=4, vol_mode="history")
    cur2 = mc.simulate_paths(calm_then_wild, n_paths=1500, seed=4, vol_mode="current")
    assert cur2[:, 1].std() > 1.5 * hist2[:, 1].std()


def test_sample_stats_vol_ratio():
    rng = np.random.default_rng(10)
    calm_now = pd.Series(np.concatenate([rng.normal(0, 0.03, 200), rng.normal(0, 0.005, 50)]))
    s = mc.sample_stats(calm_now)
    assert s["vol_ratio"] < 0.7
    assert s["ann_vol_current"] < s["ann_vol_history"]
    assert s["n_days"] == 250
    assert np.isfinite(s["skew"]) and np.isfinite(s["kurtosis"])


def test_equity_confidence_deterministic():
    r = pd.Series(np.full(100, 0.001))
    out = mc.equity_confidence(r, capital=100.0, n_paths=200, seed=1, bench_total=0.0)
    expected = 100.0 * 1.001 ** 100
    assert out["final"]["p05"] == pytest.approx(expected)
    assert out["final"]["p95"] == pytest.approx(expected)
    assert out["prob_loss"] == 0.0
    assert out["prob_beat_bench"] == 1.0
    assert out["dd_median"] == pytest.approx(0.0)


def test_robustness_narrative_reads_sane():
    out = mc.equity_confidence(pd.Series(np.full(100, 0.001)), capital=100.0, n_paths=200, seed=1, bench_total=0.5)
    text = itp.robustness_narrative(out, 100.0)
    assert "alternate histories" in text
    assert "fragile" in text  # never beats a +50% benchmark


def test_indicator_verdict_levels():
    assert itp.rsi_verdict(85)["level"] == "bad"
    assert itp.rsi_verdict(75)["level"] == "weak"
    assert itp.rsi_verdict(25)["level"] == "good"
    assert itp.rsi_verdict(50)["level"] == "ok"
    assert itp.macd_verdict(1.0, 0.5)["level"] == "good"
    assert itp.macd_verdict(1.0, 2.0)["level"] == "ok"
    assert itp.macd_verdict(-2.0, -1.0)["level"] == "weak"
    assert itp.macd_verdict(-1.0, -2.0)["level"] == "ok"
    assert itp.bollinger_verdict(1.1)["level"] == "bad"
    assert itp.bollinger_verdict(0.1)["level"] == "good"
    assert itp.volume_verdict(2.5)["level"] == "good"


def test_facts_sheet_rows():
    profile = {"sector": "Technology", "industry": "Software", "market_cap": 3.1e12,
               "trailing_pe": 70.0, "dividend_yield": 0.5}
    extras = {"last": 150.0, "year_high": 190.0, "year_low": 80.0,
              "atr_pct": 3.2, "dollar_vol": 2e9, "beta": 1.9}
    rows = itp.facts_sheet(profile, extras)
    labels = [r["label"] for r in rows]
    for expect in ["What it is", "Size", "P/E ratio", "Dividend", "52-week range", "Typical day", "Liquidity", "Beta"]:
        assert expect in labels
    pe = next(r for r in rows if r["label"] == "P/E ratio")
    assert "expensive" in pe["note"].lower()
    assert itp.facts_sheet({}, {}) == []  # sparse data never crashes


def test_vol_regime_line():
    assert "more volatile" in itp.vol_regime_line({"vol_ratio": 2.0, "ann_vol_current": 0.9})
    assert "calm" in itp.vol_regime_line({"vol_ratio": 0.5, "ann_vol_current": 0.2})
    assert "close to" in itp.vol_regime_line({"vol_ratio": 1.0, "ann_vol_current": 0.4})


def test_forecast_narrative_mentions_comparison(up_returns):
    paths = mc.simulate_paths(up_returns, n_paths=400, seed=2)
    s = mc.summarize(paths)
    best = mc.best_entry(paths)
    strat = mc.dip_buy_outcomes(paths, dip=0.05, target=0.10, stop=0.07)
    text = itp.forecast_narrative("TEST", 21, 400, s, best, strat, 5.0)
    assert "400" in text and "21 sessions" in text
    assert "not a promise" in text
