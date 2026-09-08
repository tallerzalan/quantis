import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend, LabelList, ResponsiveContainer,
} from "recharts";
import { get, post, fmt$, fmtPct, fmtNum } from "../api";
import { useFetch, ErrorNote, Loading, stagger, rise } from "../components/ui";

const PROFILE_COLORS = { Cautious: "#199e70", Balanced: "#c98500", Bold: "#3987e5", Anchored: "#9085e9" };

export default function Optimize({ wlVersion, capital, watchlist }) {
  const [selected, setSelected] = useState(null); // null = auto top-8
  const [cap, setCap] = useState(0.4);
  const [chosen, setChosen] = useState("Balanced");

  const body = useMemo(
    () => ({ capital, cap, tickers: selected }),
    [capital, cap, selected]
  );
  const { data, error, loading, reload } = useFetch(() => post("/optimize", body), [wlVersion, body]);

  const toggle = (sym) => {
    const base = selected ?? data?.tickers ?? [];
    const next = base.includes(sym) ? base.filter((t) => t !== sym) : [...base, sym];
    setSelected(next);
  };

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div variants={rise}>
        <h2 className="page-title">Portfolio optimizer</h2>
        <p className="page-sub">
          Markowitz portfolio theory: mixing assets that don't move together gets you more return for less risk.
          Pick the assets, pick your comfort level, get an exact split of your {fmt$(capital, 0)}.
        </p>
      </motion.div>

      <motion.div className="card pad-sm" variants={rise}>
        <div className="card-title">Assets in the mix — click to toggle (needs 2+)</div>
        <div className="wl-chips" style={{ flexWrap: "wrap" }}>
          {watchlist.map((t) => {
            const active = (selected ?? data?.tickers ?? []).includes(t.symbol);
            return (
              <button key={t.symbol} className="chip"
                style={{ cursor: "pointer", borderColor: active ? "var(--accent)" : undefined, color: active ? "var(--ink)" : "var(--muted)", background: active ? "var(--accent-soft)" : undefined }}
                onClick={() => toggle(t.symbol)}>
                {t.symbol}
              </button>
            );
          })}
        </div>
        <div className="controls" style={{ marginTop: 12 }}>
          <label className="field">Max % in any one name
            <select value={cap} onChange={(e) => setCap(Number(e.target.value))}>
              <option value={0.25}>25% — very diversified</option>
              <option value={0.4}>40% — balanced</option>
              <option value={0.6}>60% — concentrated</option>
              <option value={1.0}>100% — no limit</option>
            </select>
          </label>
          {selected && <button className="btn ghost sm" onClick={() => setSelected(null)}>Reset to today's top picks</button>}
        </div>
      </motion.div>

      {loading && <Loading height={340} label="Solving for the best mixes…" />}
      {error && <ErrorNote error={error} onRetry={reload} />}

      {data && !loading && (
        <>
          <div className="grid cols-4">
            {data.profiles.map((p) => (
              <motion.button key={p.name} variants={rise} className={`strat ${chosen === p.name ? "on" : ""}`} onClick={() => setChosen(p.name)}
                style={{ alignItems: "stretch" }}>
                <span className="nm" style={{ color: PROFILE_COLORS[p.name] }}>{p.name}</span>
                <span className="ds">{p.blurb}</span>
                <span className="mono" style={{ fontSize: 12.5 }}>
                  {fmtPct(p.stats.return * 100, 0)}/yr expected · ±{fmtNum(p.stats.volatility * 100, 0)}% swings
                </span>
              </motion.button>
            ))}
          </div>

          {data.profiles.filter((p) => p.name === chosen).map((p) => (
            <motion.div key={p.name} className="card" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="card-title">Your {fmt$(capital, 0)}, split the {p.name.toLowerCase()} way</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Object.entries(p.dollars).map(([t, d]) => (
                  <div key={t} style={{ display: "grid", gridTemplateColumns: "64px 1fr 90px", gap: 10, alignItems: "center" }}>
                    <span className="tick">{t}</span>
                    <div style={{ background: "var(--surface-2)", borderRadius: 6, height: 22, position: "relative", overflow: "hidden" }}>
                      <motion.div
                        initial={{ width: 0 }} animate={{ width: `${(d / capital) * 100}%` }} transition={{ type: "spring", stiffness: 70, damping: 18 }}
                        style={{ position: "absolute", inset: 0, background: PROFILE_COLORS[p.name], opacity: 0.75, borderRadius: 6 }} />
                    </div>
                    <span className="money" style={{ textAlign: "right" }}>{fmt$(d)}</span>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: 13, marginBottom: 0 }}>{p.summary}</p>
              {p.name === "Anchored" && data.black_litterman?.note && (
                <div className="explain good" style={{ marginTop: 4 }}>{data.black_litterman.note}</div>
              )}
            </motion.div>
          ))}

          <motion.div className="card" variants={rise}>
            <div className="card-title">The risk-return map — every dot is a possible portfolio</div>
            <ResponsiveContainer width="100%" height={340}>
              <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid stroke="#232322" />
                <XAxis type="number" dataKey="vol" name="Risk" unit="%" tick={{ fill: "#898781", fontSize: 11 }}
                  label={{ value: "Risk (yearly swings, %)", position: "insideBottom", offset: -4, fill: "#898781", fontSize: 12 }}
                  domain={["auto", "auto"]} tickFormatter={(v) => Math.round(v)} />
                <YAxis type="number" dataKey="ret" name="Return" unit="%" tick={{ fill: "#898781", fontSize: 11 }}
                  label={{ value: "Expected return (%/yr)", angle: -90, position: "insideLeft", fill: "#898781", fontSize: 12 }}
                  tickFormatter={(v) => Math.round(v)} />
                <RTooltip
                  contentStyle={{ background: "#2a2a28", border: "1px solid #383835", borderRadius: 8, fontSize: 12 }}
                  formatter={(v, n) => [`${Number(v).toFixed(1)}%`, n === "ret" ? "Expected return" : "Risk"]}
                  labelFormatter={() => ""} />
                <Scatter name="Efficient frontier" data={data.frontier.map((f) => ({ vol: f.volatility * 100, ret: f.return * 100 }))}
                  fill="#3987e5" line={{ stroke: "#3987e5", strokeWidth: 2 }} shape={() => null} legendType="line" />
                <Scatter name="Individual stocks" data={data.assets.map((a) => ({ vol: a.vol * 100, ret: a.ret * 100, ticker: a.ticker }))} fill="#898781">
                  <LabelList dataKey="ticker" position="top" style={{ fill: "#898781", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                </Scatter>
                {data.profiles.map((p) => (
                  <Scatter key={p.name} name={p.name} data={[{ vol: p.stats.volatility * 100, ret: p.stats.return * 100 }]}
                    fill={PROFILE_COLORS[p.name]} shape="star" legendType="star" />
                ))}
                <Legend wrapperStyle={{ fontSize: 12, color: "#898781" }} />
              </ScatterChart>
            </ResponsiveContainer>
            <p className="note" style={{ marginBottom: 0 }}>
              The blue line is the <b>efficient frontier</b> — the best possible return for each level of risk.
              Single stocks sit below it; mixing gets you above any one of them alone. Stars mark your three ready-made mixes.
            </p>
          </motion.div>
        </>
      )}
    </motion.div>
  );
}
