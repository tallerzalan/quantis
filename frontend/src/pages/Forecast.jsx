import { useState } from "react";
import { motion } from "framer-motion";
import { get, fmt$, fmtPct } from "../api";
import { useFetch, Verdict, Tile, ErrorNote, Loading, stagger, rise } from "../components/ui";
import { FanChart, DayHistogram } from "../components/charts";
import { SearchBox } from "../components/TopBar";

const HORIZONS = [
  { label: "2 weeks", days: 10 },
  { label: "1 month", days: 21 },
  { label: "3 months", days: 63 },
];

export default function Forecast({ ticker, setTicker, watchlist }) {
  const [horizon, setHorizon] = useState(21);
  const [volMode, setVolMode] = useState("current");
  const [params, setParams] = useState({ dip: 5, target: 10, stop: 7 });
  const [draft, setDraft] = useState(params);
  const { data, error, loading, reload } = useFetch(
    () => get(`/forecast/${ticker}?horizon=${horizon}&vol_mode=${volMode}&dip=${params.dip}&target=${params.target}&stop=${params.stop}`),
    [ticker, horizon, volMode, params]
  );

  const strat = data?.strategy;
  const waitWon = strat && strat.avg_ret_overall > strat.buy_now.avg_ret;
  const pct = (x) => +(x * 100).toFixed(1); // 0.07 -> 7, 0.075 -> 7.5

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div variants={rise} style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <h2 className="page-title" style={{ marginRight: 4 }}>Forecast</h2>
        <SearchBox onPick={(sym) => setTicker(sym)} placeholder="Forecast any ticker…" />
        <div className="seg">
          {HORIZONS.map((h) => (
            <button key={h.days} className={h.days === horizon ? "on" : ""} onClick={() => setHorizon(h.days)}>{h.label}</button>
          ))}
        </div>
        <div className="seg" title="Which volatility feeds the simulation. 'Today's volatility' rescales history to how wild or calm the stock is RIGHT NOW (more accurate short-term); 'full-year mix' uses the raw last year as-is.">
          <button className={volMode === "current" ? "on" : ""} onClick={() => setVolMode("current")}>Today's volatility</button>
          <button className={volMode === "history" ? "on" : ""} onClick={() => setVolMode("history")}>Full-year mix</button>
        </div>
        <div className="wl-chips" style={{ maxWidth: 420 }}>
          {watchlist.slice(0, 12).map((t) => (
            <button key={t.symbol} className="chip" style={{ cursor: "pointer", borderColor: t.symbol === ticker ? "var(--accent)" : undefined }}
              onClick={() => setTicker(t.symbol)}>
              {t.symbol}
            </button>
          ))}
        </div>
      </motion.div>

      {loading && <Loading height={420} label={`Simulating ${ticker} futures…`} />}
      {error && <ErrorNote error={error} onRetry={reload} />}

      {data && !loading && (
        <>
          <motion.div className="card" variants={rise}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                <span className="tick" style={{ fontSize: 22 }}>{data.ticker}</span>
                <span className="money" style={{ fontSize: 24 }}>{fmt$(data.last)}</span>
                <span className="dim">{data.n_paths.toLocaleString()} simulated futures · next {data.horizon} sessions</span>
              </div>
              <div className="legend">
                <span><span className="sw" style={{ background: "var(--ink-2)" }} />last 60 sessions</span>
                <span><span className="sw" style={{ background: "rgba(57,135,229,0.35)" }} />half of futures</span>
                <span><span className="sw" style={{ background: "rgba(57,135,229,0.14)" }} />90% of futures</span>
                <span><span className="sw" style={{ background: "#3987e5" }} />median path</span>
              </div>
            </div>
            <FanChart history={data.history} fan={data.fan} />
            <div className="dim" style={{ fontSize: 13, marginTop: 10, lineHeight: 1.5 }}>{data.narrative}</div>
            {data.vol_line && <div style={{ fontSize: 13, marginTop: 6, color: "var(--ink-2)" }}>{data.vol_line}</div>}
            {data.params && data.dist && (
              <div className="params-line">
                How it's computed: {data.params.n_paths.toLocaleString()} paths · {data.params.method} ·
                {" "}{data.params.block}-day blocks · sample {data.params.sample_days} sessions ·
                {" "}vol now ±{pct(data.dist.ann_vol_current)}%/yr vs ±{pct(data.dist.ann_vol_history)}%/yr over the year
                {data.dist.kurtosis > 1 ? ` · fat tails present (excess kurtosis ${data.dist.kurtosis.toFixed(1)} — extreme days happen more than a bell curve expects)` : ""}
              </div>
            )}
          </motion.div>

          <div className="grid cols-4">
            <motion.div variants={rise}><Tile label={`Chance higher in ${data.horizon} sessions`} tip="Share of simulated futures that end above today's price." value={fmtPct(data.summary.prob_up * 100, 0, false)} /></motion.div>
            <motion.div variants={rise}><Tile label="Median path" tip="Half the futures end better than this, half worse." value={fmtPct(data.summary.p50 * 100, 1)} /></motion.div>
            <motion.div variants={rise}><Tile label="Worst 1-in-20" tip="The 5th-percentile ending — a realistic bad case, not the worst possible." value={fmtPct(data.summary.p05 * 100, 1)} /></motion.div>
            <motion.div variants={rise}><Tile label="Typical low" tip="The median simulated future bottoms out here before recovering or falling further."
              value={fmt$(data.plan.limit_price)} sub={`usually around session ${data.plan.median_day}`} /></motion.div>
          </div>

          <div className="grid cols-2">
            <motion.div className="card" variants={rise}>
              <div className="card-title">When to buy</div>
              <Verdict v={data.verdict} />
              <p style={{ fontSize: 13, lineHeight: 1.55, margin: "10px 0 12px", color: "var(--ink-2)" }}>{data.verdict.detail}</p>
              <div className="plan-box">
                <div className="plan-row"><span className="dim">Patient entry</span>
                  <span>Limit order at <b className="money">{fmt$(data.plan.limit_price)}</b> ({fmtPct((data.plan.limit_price / data.last - 1) * 100, 1)})</span></div>
                <div className="plan-row"><span className="dim">Odds it fills</span>
                  <span>{fmtPct(data.plan.fill_prob * 100, 0, false)} of futures, usually by session {data.plan.median_day}–{data.plan.p75_day}</span></div>
                <div className="plan-row"><span className="dim">If it never fills</span>
                  <span>You keep your cash — reassess after {data.horizon} sessions</span></div>
                {data.next_earnings && (
                  <div className="plan-row"><span className="dim">Event risk</span>
                    <span>Earnings {data.next_earnings}{data.earnings_in != null ? ` (~${data.earnings_in} sessions)` : ""} — expect a jump either way</span></div>
                )}
              </div>
              <div style={{ marginTop: 14 }}>
                <div className="dim" style={{ fontSize: 12, marginBottom: 4 }}>When the low tends to arrive (sessions from today)</div>
                <DayHistogram hist={data.best_entry.day_hist} />
              </div>
            </motion.div>

            <motion.div className="card" variants={rise}>
              <div className="card-title">Strategy lab — buy the dip vs buy today</div>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-end", marginBottom: 12 }}>
                {[["dip", "Buy on dip of %"], ["target", "Sell at gain %"], ["stop", "Stop loss %"]].map(([k, lbl]) => (
                  <label key={k} className="field" style={{ fontSize: 11 }}>
                    {lbl}
                    <input type="number" min="1" max="30" step="0.5" value={draft[k]}
                      onChange={(e) => setDraft({ ...draft, [k]: Number(e.target.value) || draft[k] })}
                      style={{ width: 90 }} />
                  </label>
                ))}
                <button className="btn" onClick={() => setParams(draft)}>Run simulation</button>
              </div>
              <div className="vs-grid">
                <div className={`vs-col ${waitWon ? "vs-win" : ""}`}>
                  <div className="vs-name">Wait for the −{pct(strat.params.dip)}% dip</div>
                  <div className="vs-big">{fmtPct(strat.avg_ret_overall * 100, 1)}</div>
                  <div className="dim">avg outcome per future</div>
                  <div className="vs-rows">
                    <span>Fills in {fmtPct(strat.fill_rate * 100, 0, false)} of futures{strat.median_days_to_fill ? `, median ${strat.median_days_to_fill.toFixed(0)} sessions` : ""}</span>
                    <span>{strat.win_rate != null ? `${fmtPct(strat.win_rate * 100, 0, false)} of filled trades win` : "Never filled at this depth"}</span>
                  </div>
                </div>
                <div className={`vs-col ${!waitWon ? "vs-win" : ""}`}>
                  <div className="vs-name">Buy today</div>
                  <div className="vs-big">{fmtPct(strat.buy_now.avg_ret * 100, 1)}</div>
                  <div className="dim">avg outcome per future</div>
                  <div className="vs-rows">
                    <span>Always invested from session 0</span>
                    <span>{fmtPct(strat.buy_now.win_rate * 100, 0, false)} of futures end profitable</span>
                  </div>
                </div>
              </div>
              <div className="dim" style={{ fontSize: 12, marginTop: 10 }}>
                Both sides use the same exits: +{pct(strat.params.target)}% target, −{pct(strat.params.stop)}% stop, or time-out at {data.horizon} sessions.
                Unfilled limit orders count as 0% (cash).
              </div>
            </motion.div>
          </div>

          <motion.div className="card pad-sm" variants={rise}>
            <div className="dim" style={{ fontSize: 12, lineHeight: 1.5 }}>
              Simulations resample {data.ticker}'s real daily returns (block bootstrap), so fat tails and streaks survive —
              but they only know history. A merger, a scandal, or a Fed surprise is not in there. Odds, not promises.
            </div>
          </motion.div>
        </>
      )}
    </motion.div>
  );
}
