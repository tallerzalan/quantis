import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { get, post, fmt$, fmtPct, fmtNum } from "../api";
import { useFetch, Verdict, Explain, Tile, ErrorNote, Loading, DataTable, stagger, rise } from "../components/ui";
import { EquityChart } from "../components/charts";

const GRADE_COLORS = { "A+": "#0ca30c", A: "#0ca30c", "B+": "#199e70", B: "#199e70", "C+": "#c98500", C: "#c98500", D: "#d95926", "D-": "#d95926", F: "#d03b3b" };

export default function Backtest({ wlVersion, capital }) {
  const { data: meta, error: metaErr } = useFetch(() => get("/strategies"), []);
  const { data: universes } = useFetch(() => get("/universes"), []);
  const [sel, setSel] = useState("momentum");
  const [custom, setCustom] = useState(false);
  const [code, setCode] = useState("");
  const [universe, setUniverse] = useState("watchlist");
  const [params, setParams] = useState({ lookback: 20, top_n: 5, hold_days: 5, stop_mult: 1.5, slippage: 5, spread: 2, commission: 1, period: "1y" });
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  const setP = (k) => (e) => setParams((p) => ({ ...p, [k]: e.target.value }));

  const run = async () => {
    setRunning(true); setError(null);
    try {
      const body = custom
        ? { code: code || meta.template, universe, params: { ...params, capital } }
        : { strategy: sel, universe, params: { ...params, capital } };
      setResult(await post("/backtest", body));
    } catch (e) {
      setError(e);
    } finally { setRunning(false); }
  };

  if (metaErr) return <ErrorNote error={metaErr} />;
  if (!meta) return <Loading height={300} label="Loading strategies…" />;

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div variants={rise}>
        <h2 className="page-title">Backtest a strategy</h2>
        <p className="page-sub">
          Replay a rule-book over the past year of your watchlist and see what your {fmt$(capital, 0)} would have done —
          before risking a cent. Pick a built-in playbook or code your own.
        </p>
      </motion.div>

      <motion.div className="grid cols-3" variants={rise} style={{ gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))" }}>
        {meta.strategies.map((s) => (
          <button key={s.key} className={`strat ${!custom && sel === s.key ? "on" : ""}`}
            onClick={() => { setSel(s.key); setCustom(false); }}>
            <span className="nm">{s.name}</span>
            <span className="ds">{s.description}</span>
            <span className="bf">Best for: {s.best_for}</span>
          </button>
        ))}
        <button className={`strat ${custom ? "on" : ""}`} onClick={() => { setCustom(true); if (!code) setCode(meta.template); }}>
          <span className="nm">⌨️ Code your own</span>
          <span className="ds">Write the entry and exit rules yourself in Python — pandas, numpy and all the indicators are ready to use.</span>
          <span className="bf">Best for: your ideas</span>
        </button>
      </motion.div>

      <AnimatePresence>
        {custom && (
          <motion.div className="card" initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} style={{ overflow: "hidden" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, flexWrap: "wrap", gap: 8 }}>
              <div className="card-title" style={{ marginBottom: 0 }}>Your strategy — define entries and exits</div>
              <div className="seg">
                {Object.keys(meta.examples).map((name) => (
                  <button key={name} onClick={() => setCode(meta.examples[name])}>{name}</button>
                ))}
              </div>
            </div>
            <div className="cm-editor-wrap">
              <CodeMirror value={code} onChange={setCode} extensions={[python()]} theme="dark" height="260px"
                basicSetup={{ foldGutter: false, autocompletion: false }} />
            </div>
            <p className="note" style={{ marginBottom: 0 }}>
              Return <span className="mono">(entries, exits)</span> — True where a signal is known at that day's close; orders execute at the next session's open.
              Available: <span className="mono">ind.rsi · ind.ema · ind.macd · ind.atr · ind.roc · ind.bollinger_percent_b · ind.adx · ind.relative_volume · pd · np</span>.
              Stops and holding limits below still apply.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.div className="card pad-sm" variants={rise}>
        <div className="controls">
          <label className="field">Trade this basket
            <select value={universe} onChange={(e) => setUniverse(e.target.value)}>
              {(universes?.universes ?? [{ key: "watchlist", name: "My watchlist" }]).map((u) => (
                <option key={u.key} value={u.key}>{u.name}</option>
              ))}
            </select>
          </label>
          {!custom && sel === "momentum" && (
            <label className="field">Momentum lookback (days)
              <input type="number" min="5" max="120" value={params.lookback} onChange={setP("lookback")} />
            </label>
          )}
          <label className="field">Max positions
            <input type="number" min="1" max="10" value={params.top_n} onChange={setP("top_n")} />
          </label>
          <label className="field">{sel === "momentum" && !custom ? "Rebalance every (days)" : "Max hold (days)"}
            <input type="number" min="1" max="21" value={params.hold_days} onChange={setP("hold_days")} />
          </label>
          {(custom || sel !== "momentum") && (
            <label className="field">Stop-loss (× daily range)
              <input type="number" min="0.5" max="5" step="0.25" value={params.stop_mult} onChange={setP("stop_mult")} />
            </label>
          )}
          <label className="field">Slippage (bps/side)
            <input type="number" min="0" max="50" value={params.slippage} onChange={setP("slippage")} />
          </label>
          <label className="field">Full spread (bps)
            <input type="number" min="0" max="100" step="0.5" value={params.spread} onChange={setP("spread")} />
          </label>
          <label className="field">Commission (bps/side)
            <input type="number" min="0" max="50" step="0.1" value={params.commission} onChange={setP("commission")} />
          </label>
          <label className="field">History
            <select value={params.period} onChange={setP("period")}>
              <option value="6mo">6 months</option><option value="1y">1 year</option><option value="2y">2 years</option>
            </select>
          </label>
          <button className="btn" onClick={run} disabled={running}>
            {running ? "Running…" : "▶ Run backtest"}
          </button>
        </div>
      </motion.div>

      {error && <ErrorNote error={error} />}
      {running && <Loading height={200} label="Replaying history…" />}

      <AnimatePresence>
        {result && !running && (
          <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="card" style={{ display: "flex", gap: 18, alignItems: "flex-start" }}>
              <div className="grade" style={{ background: GRADE_COLORS[result.summary.grade] || "var(--baseline)" }}>
                {result.summary.grade}
              </div>
              <div>
                <h3 style={{ marginBottom: 6 }}>{result.name}</h3>
                <p style={{ margin: 0, fontSize: 13.5, lineHeight: 1.6 }}>{result.summary.narrative}</p>
                <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                  <Verdict v={result.summary.verdicts.sharpe} />
                  <Verdict v={result.summary.verdicts.alpha} />
                  <Verdict v={result.summary.verdicts.beta} />
                  <Verdict v={result.summary.verdicts.drawdown} />
                  <Verdict v={result.summary.verdicts.profit_factor} />
                </div>
              </div>
            </div>

            <div className="grid cols-4">
              <Tile label="Final value" value={fmt$(capital * (1 + (result.stats.total_return ?? 0)))} sub={fmtPct((result.stats.total_return ?? 0) * 100)} />
              <Tile label="Sharpe" tip="Return per unit of risk. Above 1 is good, above 1.5 excellent." value={fmtNum(result.stats.sharpe)} />
              <Tile label="Worst drop" tip="Biggest fall from a peak along the way." value={fmtPct((result.stats.max_drawdown ?? 0) * 100, 1, false)} />
              <Tile label={result.stats.n_trades != null ? "Win rate" : "Beta"}
                value={result.stats.n_trades != null ? (result.stats.win_rate == null ? "—" : `${Math.round(result.stats.win_rate * 100)}%`) : fmtNum(result.stats.beta)}
                sub={result.stats.n_trades != null ? `${result.stats.n_trades} trades` : "vs S&P 500"} />
            </div>

            <div className="card">
              <div className="card-title">Growth of {fmt$(capital, 0)} — {result.name} on {result.universe} ({result.tickers?.length ?? "?"} tickers)</div>
              <EquityChart equity={result.equity} bench={result.bench} names={[result.name, "SPY buy & hold"]} />
            </div>

            {result.montecarlo && (
              <div className="card">
                <div className="card-title">Robustness check — 1,000 Monte Carlo reruns</div>
                <div className="grid cols-4" style={{ marginBottom: 12 }}>
                  <Tile label="Middle outcome" tip="Median final value across the reshuffled histories."
                    value={fmt$(result.montecarlo.final.p50)} sub={`of ${fmt$(capital, 0)} start`} />
                  <Tile label="Worst 1-in-20" tip="The 5th-percentile final value — a realistic bad run of the same strategy."
                    value={fmt$(result.montecarlo.final.p05)}
                    sub={`best 1-in-20: ${fmt$(result.montecarlo.final.p95)}`} />
                  <Tile label="Chance of losing money" tip="Share of reshuffled histories that end below the starting capital."
                    value={`${Math.round(result.montecarlo.prob_loss * 100)}%`}
                    valueClass={result.montecarlo.prob_loss > 0.4 ? "down" : ""} />
                  {result.montecarlo.prob_beat_bench != null && (
                    <Tile label="Beats SPY buy & hold" tip="Share of reshuffled histories that end above simply holding SPY."
                      value={`${Math.round(result.montecarlo.prob_beat_bench * 100)}%`}
                      valueClass={result.montecarlo.prob_beat_bench >= 0.5 ? "up" : "down"} />
                  )}
                </div>
                <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--ink-2)" }}>{result.montecarlo.narrative}</p>
              </div>
            )}

            {result.trades?.length > 0 && (
              <div className="card">
                <div className="card-title">Closed trades (most recent {result.trades.length})</div>
                <DataTable
                  initialSort={{ key: "exit_date", dir: -1 }}
                  columns={[
                    { key: "ticker", label: "Ticker", render: (r) => <span className="tick">{r.ticker}</span> },
                    { key: "signal_date", label: "Signal" },
                    { key: "entry_date", label: "In" },
                    { key: "exit_date", label: "Out" },
                    { key: "entry", label: "Entry", render: (r) => fmt$(r.entry) },
                    { key: "exit", label: "Exit", render: (r) => fmt$(r.exit) },
                    { key: "return_pct", label: "Return", render: (r) => fmtPct(r.return_pct * 100), className: (r) => (r.return_pct >= 0 ? "up mono" : "down mono") },
                    { key: "pnl", label: "P&L", render: (r) => fmt$(r.pnl), className: (r) => (r.pnl >= 0 ? "up mono" : "down mono") },
                    { key: "costs", label: "Costs", render: (r) => fmt$(r.costs) },
                    { key: "reason", label: "Exit because", render: (r) => ({ stop: "stop-loss", signal: "sell signal", timeout: "time limit" }[r.reason] || r.reason) },
                    { key: "days", label: "Days" },
                  ]}
                  rows={result.trades}
                  max={100}
                />
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
