"""Plain-English interpretation layer.

Every quantitative result resolves to a *verdict*: a level (great/good/ok/
weak/bad), a short label, and one sentence saying what it means for the
user's money. The UI renders these directly so numbers are never left
uninterpreted.
"""
from __future__ import annotations

import numpy as np


def verdict(level: str, label: str, detail: str) -> dict:
    return {"level": level, "label": label, "detail": detail}


def _fin(x) -> bool:
    return x is not None and np.isfinite(x)


def sharpe_verdict(s: float) -> dict:
    if not _fin(s):
        return verdict("ok", "Not enough data", "Too few days to judge risk-adjusted return.")
    if s >= 1.5:
        return verdict("great", "Excellent", f"Sharpe {s:.2f}: you earn {s:.1f} units of return per unit of risk — professional-grade.")
    if s >= 1.0:
        return verdict("good", "Good", f"Sharpe {s:.2f}: solidly paid for the risk you take.")
    if s >= 0.5:
        return verdict("ok", "Acceptable", f"Sharpe {s:.2f}: positive but modest reward for the risk.")
    if s >= 0:
        return verdict("weak", "Weak", f"Sharpe {s:.2f}: barely compensated for the risk taken.")
    return verdict("bad", "Losing", f"Sharpe {s:.2f}: this took risk and lost money doing it.")


def beta_verdict(b: float) -> dict:
    if not _fin(b):
        return verdict("ok", "Unknown", "Not enough overlapping data with the market.")
    if b < 0.5:
        return verdict("good", "Defensive", f"Beta {b:.2f}: moves about {b:.1f}× the market — cushioned in sell-offs.")
    if b <= 1.2:
        return verdict("ok", "Market-like", f"Beta {b:.2f}: rises and falls roughly with the S&P 500.")
    if b <= 2.0:
        return verdict("weak", "Aggressive", f"Beta {b:.2f}: swings ~{b:.1f}× the market — bigger gains AND bigger losses.")
    return verdict("bad", "Very aggressive", f"Beta {b:.2f}: moves ~{b:.1f}× the market. A 5% market drop ≈ {b * 5:.0f}% hit here.")


def alpha_verdict(a: float) -> dict:
    if not _fin(a):
        return verdict("ok", "Unknown", "Not enough data to separate skill from market exposure.")
    pct = a * 100
    if pct >= 10:
        return verdict("great", "Strong alpha", f"+{pct:.0f}%/yr beyond what market exposure explains — genuine outperformance.")
    if pct >= 2:
        return verdict("good", "Positive alpha", f"+{pct:.0f}%/yr above its fair market-driven return.")
    if pct >= -2:
        return verdict("ok", "No edge", f"{pct:+.0f}%/yr — performance is what market exposure alone would deliver.")
    return verdict("bad", "Negative alpha", f"{pct:+.0f}%/yr below its market-driven fair return — it underperforms its risk.")


def drawdown_verdict(dd: float) -> dict:
    if not _fin(dd):
        return verdict("ok", "Unknown", "No drawdown history yet.")
    pct = abs(dd) * 100
    if pct <= 10:
        return verdict("great", "Shallow dips", f"Worst peak-to-trough fall was {pct:.0f}% — easy to sit through.")
    if pct <= 20:
        return verdict("good", "Moderate dips", f"Worst fall was {pct:.0f}% of your money — uncomfortable but recoverable.")
    if pct <= 35:
        return verdict("weak", "Deep dips", f"At its worst this lost {pct:.0f}% from the peak. Could you hold through that?")
    return verdict("bad", "Severe dips", f"A {pct:.0f}% collapse from the peak — most people bail out before it recovers.")


def var_sentence(var_95: float, capital: float) -> str:
    if not _fin(var_95):
        return "Not enough history to estimate a daily worst case."
    return (f"On the worst 1-in-20 days, expect to lose about ${var_95 * capital:.2f} "
            f"of ${capital:.0f} ({var_95 * 100:.1f}%) in a single day.")


def profit_factor_verdict(pf: float) -> dict:
    if not _fin(pf):
        return verdict("ok", "No trades", "No closed trades to judge.")
    if pf >= 2:
        return verdict("great", "Very profitable", f"Winners paid {pf:.1f}× what losers cost.")
    if pf >= 1.3:
        return verdict("good", "Profitable", f"Every $1 lost on bad trades was offset by ${pf:.2f} won on good ones.")
    if pf >= 1.0:
        return verdict("ok", "Break-even-ish", f"Profit factor {pf:.2f} — wins barely cover losses after costs.")
    return verdict("bad", "Losing system", f"Profit factor {pf:.2f} — losses outweigh wins.")


def backtest_grade(stats: dict) -> str:
    pts = 0
    s = stats.get("sharpe", np.nan)
    if _fin(s):
        pts += 3 if s >= 1.5 else 2 if s >= 1.0 else 1 if s >= 0.5 else 0 if s >= 0 else -2
    a = stats.get("alpha", np.nan)
    if _fin(a):
        pts += 2 if a >= 0.05 else 1 if a > 0 else -1
    dd = stats.get("max_drawdown", np.nan)
    if _fin(dd):
        pts += 1 if dd >= -0.15 else 0 if dd >= -0.30 else -1
    pf = stats.get("profit_factor", np.nan)
    if _fin(pf):
        pts += 1 if pf >= 1.3 else 0
    scale = {7: "A+", 6: "A", 5: "B+", 4: "B", 3: "C+", 2: "C", 1: "D", 0: "D-"}
    return scale.get(max(min(pts, 7), 0), "F") if pts >= 0 else "F"


def backtest_summary(stats: dict, capital: float, bench_total: float | None) -> dict:
    total = stats.get("total_return", 0.0)
    end_val = capital * (1 + total)
    lines = [f"${capital:.0f} would have become ${end_val:.2f} ({total * 100:+.1f}%)."]
    if _fin(bench_total):
        diff = (total - bench_total) * 100
        lines.append(
            f"Simply holding SPY: {bench_total * 100:+.1f}% — this strategy "
            + (f"beat it by {diff:.1f} points." if diff > 0 else f"trailed it by {abs(diff):.1f} points.")
        )
    dd = stats.get("max_drawdown")
    if _fin(dd):
        lines.append(f"Along the way it fell as much as {abs(dd) * 100:.0f}% from a peak — "
                     "that's the ride you'd have had to sit through.")
    wr = stats.get("win_rate")
    if _fin(wr):
        lines.append(f"{wr * 100:.0f}% of trades won; losing trades are normal and expected — "
                     "the stop-loss keeps them small.")
    return {
        "grade": backtest_grade(stats),
        "narrative": " ".join(lines),
        "verdicts": {
            "sharpe": sharpe_verdict(stats.get("sharpe")),
            "alpha": alpha_verdict(stats.get("alpha")),
            "beta": beta_verdict(stats.get("beta")),
            "drawdown": drawdown_verdict(stats.get("max_drawdown")),
            "profit_factor": profit_factor_verdict(stats.get("profit_factor")),
        },
    }


def idea_reason(row) -> str:
    """One plain sentence explaining why a ticker scored high."""
    parts = []
    if row.get("momentum", 0) > 0.5:
        parts.append(f"strong recent momentum ({row.get('roc20', 0):+.0f}% over 20 days)")
    if row.get("trend", 0) > 0.3:
        parts.append("a confirmed uptrend (price above its moving averages)")
    if row.get("meanrev", 0) > 0.5:
        parts.append(f"a short-term dip in that uptrend (RSI-2 at {row.get('rsi2', 0):.0f}) — a buy-the-dip setup")
    if row.get("volume_score", 0) > 0.5:
        parts.append(f"above-normal buying volume ({row.get('rvol', 1):.1f}× average)")
    if not parts:
        parts.append("the best overall balance of momentum, trend and volume in your watchlist right now")
    reason = "; ".join(parts)
    return reason[0].upper() + reason[1:] + "."


def regime(spy_above_ema50: bool, breadth: float) -> dict:
    """Market regime from SPY trend + % of watchlist above its 20-day EMA."""
    b = breadth * 100
    if spy_above_ema50 and breadth >= 0.55:
        return verdict("good", "Risk-on",
                       f"The S&P 500 is in an uptrend and {b:.0f}% of your watchlist is above its 20-day average. Conditions favor buying.")
    if not spy_above_ema50 and breadth <= 0.45:
        return verdict("bad", "Risk-off",
                       f"The S&P 500 is below its 50-day trend and only {b:.0f}% of your watchlist is holding up. Consider smaller positions or waiting.")
    return verdict("ok", "Mixed",
                   f"Signals disagree ({b:.0f}% of your watchlist is in short-term uptrends). Trade smaller and be selective.")


def optimizer_summary(name: str, stats: dict, dollars: dict, fell_back: bool, capital: float) -> str:
    top = max(dollars, key=dollars.get) if dollars else None
    s = (f"This split targets {stats['return'] * 100:+.0f}%/yr with swings of about "
         f"±{stats['volatility'] * 100:.0f}%/yr (Sharpe {stats['sharpe']:.2f}).")
    if top:
        s += f" Biggest position: ${dollars[top]:.2f} in {top}."
    if fell_back:
        s = "Nothing on this window beat the risk-free rate, so this is the lowest-risk mix instead. " + s
    return s


# ------------------------------------------------- significant-move events

def odds_phrase(pvalue: float) -> str:
    """Turn a p-value into 'about 1 trading day in N' language."""
    if not _fin(pvalue) or pvalue <= 0:
        return "essentially never by chance alone"
    days = 1.0 / pvalue
    if days < 40:
        return f"about 1 trading day in {days:.0f}"
    years = days / 252.0
    if years < 1.5:
        return f"about once a year ({days:.0f} trading days)"
    if years < 1000:
        return f"roughly once every {years:.0f} years of trading"
    return "basically never — a day like this is news, not noise"


CATALYST_LABELS = {
    "earnings": "Earnings report",
    "split": "Stock split",
    "dividend": "Dividend ex-date",
    "news": "News",
    "market": "Market-wide move",
    "unknown": "No identified catalyst",
}


def event_story(ev: dict, ticker: str) -> dict:
    """One plain-English explanation of a statistically significant move."""
    pct = ev["ret"] * 100
    verb = "jumped" if ev["ret"] > 0 else "dropped"
    sigma = abs(ev["z"])
    lines = [
        f"{ticker} {verb} {pct:+.1f}% — a {sigma:.1f}σ move vs its own recent volatility. "
        f"If daily swings followed a bell curve, a day this extreme would happen {odds_phrase(ev['pvalue'])}."
    ]
    kind = ev.get("catalyst", "unknown")
    if kind == "earnings":
        lines.append("It was an earnings reaction — results landed that morning or the evening before, "
                     "and surprises there are the classic cause of gaps this large.")
    elif kind == "split":
        lines.append("A stock split took effect that day; the price change is mostly mechanical, not a repricing.")
    elif kind == "dividend":
        lines.append("The stock traded ex-dividend that day, which mechanically lowers the price.")
    elif kind == "news" and ev.get("headlines"):
        lines.append(f"Likeliest driver in the headlines: “{ev['headlines'][0]['title']}”.")
    elif kind == "market":
        b = ev.get("bench_ret")
        lines.append("This was mostly a market-wide day"
                     + (f" — the S&P 500 moved {b * 100:+.1f}% in the same direction." if _fin(b) else "."))
    else:
        lines.append("No catalyst shows up in the data we have (free headlines only cover recent weeks). "
                     "Moves like this usually trace back to news, analyst actions, or one large buyer/seller.")
    rvol = ev.get("rvol")
    if _fin(rvol):
        if rvol >= 2:
            lines.append(f"Volume ran {rvol:.1f}× normal — real conviction behind the move, not thin-market noise.")
        elif rvol < 0.8:
            lines.append(f"Volume was only {rvol:.1f}× normal — a big move on light trading carries less signal.")
    if ev.get("market_move") and kind not in ("market",):
        lines.append("The broad market also moved the same way that day, which amplified it.")
    return {
        "title": f"{pct:+.1f}% · {sigma:.1f}σ",
        "catalyst_label": CATALYST_LABELS.get(kind, kind),
        "story": " ".join(lines),
    }


# --------------------------------------------------- forecast / entry timing

def entry_verdict(ctx: dict) -> dict:
    """Buy-low timing call from current dip context + simulated dip odds.

    ctx keys: rsi14, pctb, off_high (fraction below 20-day high, <= 0),
    above_ema50 (bool), earnings_in (sessions until earnings, or None).
    """
    rsi, pctb, off = ctx.get("rsi14"), ctx.get("pctb"), ctx.get("off_high")
    uptrend = bool(ctx.get("above_ema50"))
    oversold = (_fin(rsi) and rsi < 35) or (_fin(pctb) and pctb < 0.15) or (_fin(off) and off < -0.07)
    overbought = (_fin(rsi) and rsi > 70) or (_fin(pctb) and pctb > 0.90)

    if oversold and uptrend:
        v = verdict("good", "Buy zone", "Already trading at a discount to its own recent range while the bigger "
                    "trend is still up — the exact setup a buy-low strategy wants.")
    elif oversold:
        v = verdict("weak", "Falling knife", "It's cheap because it's in a downtrend. Cheap can get cheaper — "
                    "wait for the price to reclaim its 50-day trend before buying the dip.")
    elif overbought:
        v = verdict("weak", "Chasing", "Near the top of its recent range. Buying high is the opposite of the plan — "
                    "the simulations below show what patience usually gets you.")
    else:
        v = verdict("ok", "No rush", "Mid-range: neither stretched nor on sale. A limit order below today's price "
                    "usually gets filled — let the price come to you.")
    ei = ctx.get("earnings_in")
    if ei is not None and _fin(ei):
        v["detail"] += (f" Heads-up: earnings land in ~{int(ei)} trading sessions — expect a jump in either "
                        "direction, so size smaller if you hold through it.")
        v["earnings_warning"] = True
    return v


def forecast_narrative(ticker: str, horizon: int, n_paths: int, summary: dict,
                       best: dict, strat: dict, dip_pct: float) -> str:
    s = (f"We replayed {ticker}'s own trading history {n_paths:,} times over the next {horizon} sessions. "
         f"The price ends higher in {summary['prob_up'] * 100:.0f}% of those futures "
         f"(median {summary['p50'] * 100:+.1f}%, worst 1-in-20 {summary['p05'] * 100:+.1f}%). ")
    s += (f"The typical future bottoms out around session {best['median_day']} at "
          f"{(best['median_low'] - 1) * 100:.1f}% below today. ")
    wait_avg, now_avg = strat["avg_ret_overall"], strat["buy_now"]["avg_ret"]
    if strat["fill_rate"] == 0:
        s += f"A limit order {dip_pct:.0f}% below today never filled in these futures — that dip is bigger than this stock usually gives."
    elif wait_avg > now_avg:
        s += (f"Waiting for a {dip_pct:.0f}% dip beat buying today ({wait_avg * 100:+.1f}% vs {now_avg * 100:+.1f}% "
              f"average per future) — patience gets paid here.")
    else:
        s += (f"Buying today beat waiting for a {dip_pct:.0f}% dip ({now_avg * 100:+.1f}% vs {wait_avg * 100:+.1f}% "
              f"average per future) — in the futures that never dipped, the price ran away without you.")
    return s + (" These are odds measured from this stock's real history — not a promise about next week.")


# ------------------------------------------------------- indicator readouts

def rsi_verdict(rsi: float) -> dict:
    if not _fin(rsi):
        return verdict("ok", "RSI —", "Not enough data for RSI yet.")
    if rsi >= 80:
        return verdict("bad", f"RSI {rsi:.0f} · very overbought", "Extremely stretched — buying here is chasing; pullbacks usually follow.")
    if rsi >= 70:
        return verdict("weak", f"RSI {rsi:.0f} · overbought", "Near the top of its momentum range — a poor entry for a buy-low plan.")
    if rsi <= 20:
        return verdict("good", f"RSI {rsi:.0f} · very oversold", "Deeply washed out — a dip-buyer's zone IF the bigger trend is still up.")
    if rsi <= 30:
        return verdict("good", f"RSI {rsi:.0f} · oversold", "In dip territory — attractive for buy-low entries when the trend holds.")
    return verdict("ok", f"RSI {rsi:.0f} · neutral", "Momentum is mid-range: no stretch in either direction.")


def macd_verdict(hist: float, prev_hist: float | None = None) -> dict:
    if not _fin(hist):
        return verdict("ok", "MACD —", "Not enough data for MACD yet.")
    rising = _fin(prev_hist) and hist > prev_hist
    if hist > 0:
        return (verdict("good", "MACD · bullish & building", "Upward momentum and it's still accelerating.")
                if rising else
                verdict("ok", "MACD · bullish but fading", "Still positive, but momentum is cooling — trend may be tiring."))
    return (verdict("ok", "MACD · bearish but improving", "Still negative, but the decline is slowing — watch for a turn.")
            if rising else
            verdict("weak", "MACD · bearish", "Downward momentum is in control right now."))


def bollinger_verdict(pctb: float) -> dict:
    if not _fin(pctb):
        return verdict("ok", "Bands —", "Not enough data for Bollinger Bands yet.")
    if pctb > 1.0:
        return verdict("bad", "Above the top band", "Trading outside its normal 2σ range — statistically stretched; snaps back more often than not.")
    if pctb > 0.85:
        return verdict("weak", "At the top band", "Pressing the ceiling of its usual range — late to buy.")
    if pctb < 0.0:
        return verdict("weak", "Below the bottom band", "Panic territory: outside its normal range to the downside. Bounces are common but so are falling knives — check the trend.")
    if pctb < 0.2:
        return verdict("good", "Near the bottom band", "At the cheap end of its usual range — the dip a buy-low strategy waits for.")
    return verdict("ok", "Mid-band", "Sitting in the middle of its normal trading range.")


def volume_verdict(rvol: float) -> dict:
    if not _fin(rvol):
        return verdict("ok", "Volume —", "No volume data.")
    if rvol >= 2.0:
        return verdict("good", f"Volume {rvol:.1f}× normal", "Heavy trading — moves on volume like this carry real conviction.")
    if rvol >= 1.3:
        return verdict("ok", f"Volume {rvol:.1f}× normal", "Somewhat busier than usual.")
    if rvol <= 0.6:
        return verdict("ok", f"Volume {rvol:.1f}× normal", "Quiet tape — moves on thin volume are less trustworthy.")
    return verdict("ok", f"Volume {rvol:.1f}× normal", "Typical trading activity.")


def vol_regime_line(stats: dict) -> str:
    ratio = stats.get("vol_ratio")
    cur = stats.get("ann_vol_current")
    if not _fin(ratio) or not _fin(cur):
        return ""
    if ratio >= 1.4:
        return (f"Right now it's trading {ratio:.1f}× more volatile than its 1-year normal "
                f"(±{cur * 100:.0f}%/yr pace) — expect wider swings than the past year suggests.")
    if ratio <= 0.7:
        return (f"Right now it's unusually calm — {ratio:.1f}× its 1-year normal volatility "
                f"(±{cur * 100:.0f}%/yr pace). Quiet periods can end abruptly.")
    return f"Current volatility (±{cur * 100:.0f}%/yr pace) is close to its 1-year normal."


# ---------------------------------------------------------------- fact sheet

def _cap_note(mc: float) -> tuple[str, str]:
    if mc >= 200e9:
        return f"${mc / 1e12:.2f}T" if mc >= 1e12 else f"${mc / 1e9:.0f}B", "A giant — moves slower, hard to kill."
    if mc >= 10e9:
        return f"${mc / 1e9:.0f}B", "Large company — established, still swings."
    if mc >= 2e9:
        return f"${mc / 1e9:.1f}B", "Mid-cap — bigger swings both ways."
    return f"${mc / 1e6:.0f}M", "Small company — expect violent moves."


def facts_sheet(facts: dict, extras: dict) -> list[dict]:
    """Rows of {label, value, note} for non-quant readers. `facts` comes from
    Yahoo profile data (may be sparse), `extras` from our own price history:
    last, year_high, year_low, atr_pct, dollar_vol, beta."""
    rows = []
    if facts.get("sector"):
        rows.append({"label": "What it is", "value": facts.get("industry") or facts["sector"],
                     "note": f"Sector: {facts['sector']}."})
    mc = facts.get("market_cap")
    if _fin(mc) and mc > 0:
        val, note = _cap_note(mc)
        rows.append({"label": "Size", "value": val, "note": note})
    pe = facts.get("trailing_pe")
    if _fin(pe) and pe > 0:
        note = ("Very expensive vs earnings — priced for a big future; disappointments hit hard." if pe > 60
                else "Pricier than the market average (~25) — some growth is baked in." if pe > 30
                else "Around market-average pricing." if pe > 15
                else "Cheap vs earnings — either a bargain or the market doubts the business.")
        rows.append({"label": "P/E ratio", "value": f"{pe:.0f}", "note": note})
    elif facts and "trailing_pe" in facts:
        rows.append({"label": "P/E ratio", "value": "—",
                     "note": "No meaningful P/E — little or no profit yet, so the price is a bet on the future."})
    dy = facts.get("dividend_yield")
    if _fin(dy) and dy > 0:
        rows.append({"label": "Dividend", "value": f"{dy:.1f}%/yr",
                     "note": "Pays you to hold it — rare among fast movers."})
    last, yh, yl = extras.get("last"), extras.get("year_high"), extras.get("year_low")
    if all(_fin(x) for x in (last, yh, yl)) and yh > yl:
        pos = (last - yl) / (yh - yl) * 100
        off = (last / yh - 1) * 100
        note = ("Near its 52-week high — strong, but little discount on offer." if pos > 85
                else "Near its 52-week low — cheap, but ask why before catching it." if pos < 15
                else f"{abs(off):.0f}% below its 52-week high.")
        rows.append({"label": "52-week range", "value": f"${yl:,.2f} – ${yh:,.2f}",
                     "note": f"Now at the {pos:.0f}% mark of that range. {note}"})
    atr_pct = extras.get("atr_pct")
    if _fin(atr_pct):
        d = extras.get("last", 0) * atr_pct / 100
        rows.append({"label": "Typical day", "value": f"±{atr_pct:.1f}% (${d:,.2f})",
                     "note": "Its average daily wiggle — size stops and expectations to this, not to hope."})
    dv = extras.get("dollar_vol")
    if _fin(dv) and dv > 0:
        val = f"${dv / 1e9:.1f}B/day" if dv >= 1e9 else f"${dv / 1e6:.0f}M/day"
        rows.append({"label": "Liquidity", "value": val,
                     "note": "Dollar volume traded daily — plenty for any small account." if dv > 50e6
                     else "Thinly traded — orders can move the price; use limits."})
    beta = extras.get("beta")
    if _fin(beta):
        rows.append({"label": "Beta", "value": f"{beta:.2f}",
                     "note": beta_verdict(beta)["detail"]})
    return rows


def robustness_narrative(mcs: dict, capital: float) -> str:
    """One paragraph for the backtest Monte Carlo block."""
    f = mcs["final"]
    s = (f"To test whether this result was skill or one lucky ordering of days, we reshuffled the strategy's own "
         f"daily returns into {mcs['n_paths']:,} alternate histories. The middle outcome is "
         f"${f['p50']:,.2f}; 9 in 10 land between ${f['p05']:,.2f} and ${f['p95']:,.2f}. ")
    s += f"It loses money in {mcs['prob_loss'] * 100:.0f}% of histories. "
    if mcs.get("prob_beat_bench") is not None:
        pb = mcs["prob_beat_bench"] * 100
        s += (f"It beats simply holding SPY in {pb:.0f}% of them — "
              + ("a genuinely robust edge." if pb >= 65 else
                 "better than a coin flip, not a slam dunk." if pb >= 50 else
                 "less than a coin flip: the backtest's win looks fragile."))
    return s


def cvar_verdict(cv: float) -> dict:
    if not _fin(cv):
        return verdict("ok", "Unknown", "Not enough data for a tail-loss estimate.")
    pct = cv * 100
    if pct < 3:
        return verdict("great", "Contained tail", f"On its worst days the average loss is ~{pct:.1f}% — mild.")
    if pct < 5:
        return verdict("good", "Moderate tail", f"When it's a bad day, you lose ~{pct:.1f}% on average.")
    if pct < 8:
        return verdict("weak", "Fat tail", f"Bad days average ~{pct:.1f}% — the losses cluster hard.")
    return verdict("bad", "Dangerous tail", f"Its worst days average ~{pct:.1f}% — brutal left-tail risk.")


def calmar_verdict(c: float) -> dict:
    if not _fin(c):
        return verdict("ok", "Unknown", "Not enough history for a Calmar ratio.")
    if c >= 1:
        return verdict("great", "Great pain-adjusted", f"Calmar {c:.2f}: yearly return exceeds its worst drawdown.")
    if c >= 0.5:
        return verdict("good", "Solid", f"Calmar {c:.2f}: decent reward for the deepest drop endured.")
    if c >= 0:
        return verdict("weak", "Thin", f"Calmar {c:.2f}: the return barely justifies the worst fall.")
    return verdict("bad", "Negative", f"Calmar {c:.2f}: it lost money and still had drawdowns.")


def downbeta_verdict(db: float) -> dict:
    if not _fin(db):
        return verdict("ok", "Unknown", "Not enough down-market days to measure.")
    if db < 0.8:
        return verdict("good", "Cushioned in crashes", f"Down-beta {db:.2f}: falls less than the market when it drops.")
    if db <= 1.15:
        return verdict("ok", "Falls with the market", f"Down-beta {db:.2f}: about matches the market on down days.")
    return verdict("bad", "Amplifies crashes", f"Down-beta {db:.2f}: drops harder than the market in sell-offs.")


def factor_summary(exp: dict) -> str:
    """One-line read of a factor-exposure regression result."""
    if not exp or "betas" not in exp:
        return "Not enough history to attribute this to factors."
    betas = exp["betas"]
    labels = {"market": "the market", "size": "small-caps", "value": "value",
              "momentum": "momentum", "quality": "quality", "lowvol": "low-volatility"}
    mkt = betas.get("market")
    parts = []
    if mkt is not None:
        parts.append(f"moves about {mkt:.2f}× with the market")
    tilts = sorted(((k, v) for k, v in betas.items() if k != "market"),
                   key=lambda kv: -abs(kv[1]))[:2]
    for k, v in tilts:
        if abs(v) < 0.05:
            continue
        parts.append(f"{'tilts toward' if v > 0 else 'leans against'} {labels.get(k, k)}")
    r2 = exp.get("r2")
    tail = f" Factors explain {r2 * 100:.0f}% of its moves." if _fin(r2) else ""
    return (", ".join(parts).capitalize() + "." + tail) if parts else "No strong factor tilts." + tail


def sector_summary(alloc: list) -> str:
    if not alloc:
        return "No sector data available."
    top = alloc[0]
    line = f"Most concentrated in {top['sector']} at {top['weight'] * 100:.0f}% of the book."
    if len(alloc) == 1 or top["weight"] > 0.6:
        line += " That's a heavy single-sector bet — a shock there hits the whole portfolio."
    elif len(alloc) >= 4:
        line += f" Spread across {len(alloc)} sectors, which softens any single-sector shock."
    return line


def bl_summary(delta: float) -> str:
    return ("Black-Litterman starts from the return the market's own weights imply "
            "(the equilibrium), then nudges it with Quantis's expected-return views — "
            "so the mix stays anchored to the market instead of chasing noisy estimates.")


METRIC_INFO = {
    "sharpe": "Return earned per unit of risk taken. Above 1 is good, above 1.5 is excellent, below 0 means losing money.",
    "sortino": "Like Sharpe, but only counts downside swings as risk. Higher is better.",
    "down_beta": "Beta measured only on days the market fell — how much a name amplifies losses. Below 1 is defensive.",
    "calmar": "Annual return divided by the worst drawdown. Above 1 means yearly gains exceed the deepest fall.",
    "cvar_95": "Expected shortfall: the average loss on the worst 1-in-20 days (worse than VaR, and more honest about tails).",
    "cf_var_95": "Value-at-Risk adjusted for skew and fat tails — closer to how stocks actually crash than the normal-curve VaR.",
    "omega": "Probability-weighted gains over losses. Above 1 means the upside outweighs the downside.",
    "r2": "How much of a stock's movement the factor model explains (0–100%). High = it's driven by broad factors, not stock-specific news.",
    "beta": "How much this moves when the market moves. 1.0 = same as S&P 500; 2.0 = twice the swings, both directions.",
    "alpha": "Extra return per year beyond what market exposure explains. Positive alpha = genuine outperformance.",
    "max_drawdown": "The worst peak-to-trough loss. The pain you'd have had to sit through without selling.",
    "var_95": "Value-at-Risk: the loss you'd expect on the worst 1-in-20 days.",
    "volatility": "How much the value swings over a year. Higher = wilder ride.",
    "win_rate": "Share of trades that made money. Even 40-60% wins profitably if winners run bigger than losers.",
    "profit_factor": "Total $ won ÷ total $ lost. Above 1.3 is a healthy system.",
    "cagr": "Compound annual growth rate — the smoothed yearly return.",
    "edge": "Composite 0-100 rank vs your watchlist: momentum + trend + dip-buying setup + volume. 100 = best right now.",
    "rsi2": "2-day RSI: below ~10 means very oversold short-term (a dip). Works best inside an uptrend.",
    "atr": "Average True Range - how many dollars this typically moves per day. Used to size the stop-loss.",
}
