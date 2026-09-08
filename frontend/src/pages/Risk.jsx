import { useState } from "react";
import { motion } from "framer-motion";
import {
  ResponsiveContainer, ScatterChart, Scatter, XAxis, YAxis, ZAxis, CartesianGrid,
  Tooltip as RTooltip, Cell, LabelList, LineChart, Line, AreaChart, Area, ReferenceLine,
} from "recharts";
import { get, fmtPct, fmtNum } from "../api";
import { useFetch, ErrorNote, Loading, DataTable, InfoTip, stagger, rise } from "../components/ui";
import { Heatmap } from "../components/charts";

const LEVEL_COLOR = { great: "var(--great)", good: "var(--good)", ok: "var(--ok)", weak: "var(--weak)", bad: "var(--bad)" };

function RiskReturnScatter({ rows, goChart }) {
  const pts = rows.filter((r) => r.volatility != null && r.ann_return != null)
    .map((r) => ({ x: r.volatility * 100, y: r.ann_return * 100, z: Math.max(0.2, r.sharpe || 0), ticker: r.ticker, level: r.sharpe_level }));
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ScatterChart margin={{ top: 12, right: 24, bottom: 16, left: 4 }}>
        <CartesianGrid stroke="var(--line)" />
        <XAxis type="number" dataKey="x" name="Volatility" unit="%" tick={{ fill: "var(--muted)", fontSize: 11 }}
          tickFormatter={(v) => Math.round(v)} label={{ value: "Risk (yearly volatility, %)", position: "insideBottom", offset: -6, fill: "var(--muted)", fontSize: 12 }} />
        <YAxis type="number" dataKey="y" name="Return" unit="%" tick={{ fill: "var(--muted)", fontSize: 11 }}
          tickFormatter={(v) => Math.round(v)} label={{ value: "Return (%/yr)", angle: -90, position: "insideLeft", fill: "var(--muted)", fontSize: 12 }} />
        <ZAxis type="number" dataKey="z" range={[40, 300]} />
        <ReferenceLine y={0} stroke="var(--baseline)" />
        <RTooltip cursor={{ strokeDasharray: "3 3", stroke: "var(--baseline)" }}
          content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0].payload;
            return (
              <div style={{ background: "var(--surface-3)", border: "1px solid var(--baseline)", borderRadius: 8, padding: "7px 10px", fontSize: 12 }}>
                <div className="tick">{d.ticker}</div>
                <div style={{ color: "var(--ink-2)" }}>{d.y.toFixed(0)}%/yr return · {d.x.toFixed(0)}% risk</div>
              </div>
            );
          }} />
        <Scatter data={pts} onClick={(e) => e?.ticker && goChart(e.ticker)} cursor="pointer">
          {pts.map((p, i) => <Cell key={i} fill={LEVEL_COLOR[p.level] || "var(--muted)"} fillOpacity={0.85} />)}
          <LabelList dataKey="ticker" position="top" style={{ fill: "var(--muted)", fontSize: 10, fontFamily: "var(--mono)" }} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function RiskDetail({ ticker }) {
  const { data, loading } = useFetch(() => get(`/risk/detail/${ticker}`), [ticker]);
  if (loading) return <Loading height={220} />;
  if (!data) return null;
  return (
    <div className="grid cols-2">
      <div>
        <div className="note" style={{ marginBottom: 6 }}>Rolling beta (63-day) — how its market sensitivity drifts over time</div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={data.rolling_beta} margin={{ top: 6, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis dataKey="date" tick={{ fill: "var(--muted)", fontSize: 10 }} minTickGap={48} tickLine={false} />
            <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} tickFormatter={(v) => v.toFixed(1)} />
            <ReferenceLine y={1} stroke="var(--baseline)" strokeDasharray="3 3" />
            <RTooltip contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--baseline)", borderRadius: 8, fontSize: 12 }}
              formatter={(v) => [fmtNum(v, 2), "beta"]} />
            <Line type="monotone" dataKey="beta" stroke="var(--accent)" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div>
        <div className="note" style={{ marginBottom: 6 }}>Underwater curve — how far below its peak it has been</div>
        <ResponsiveContainer width="100%" height={200}>
          <AreaChart data={data.drawdown} margin={{ top: 6, right: 12, bottom: 4, left: -8 }}>
            <CartesianGrid stroke="var(--line)" />
            <XAxis dataKey="date" tick={{ fill: "var(--muted)", fontSize: 10 }} minTickGap={48} tickLine={false} />
            <YAxis tick={{ fill: "var(--muted)", fontSize: 10 }} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
            <RTooltip contentStyle={{ background: "var(--surface-3)", border: "1px solid var(--baseline)", borderRadius: 8, fontSize: 12 }}
              formatter={(v) => [fmtPct(v * 100, 1, false), "drawdown"]} />
            <Area type="monotone" dataKey="dd" stroke="var(--down)" fill="var(--down)" fillOpacity={0.18} strokeWidth={1.5} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function Risk({ wlVersion, goChart, watchlist }) {
  const { data, error, loading, reload } = useFetch(() => get("/risk"), [wlVersion]);
  const [corrSel, setCorrSel] = useState(null);
  const [detailTicker, setDetailTicker] = useState(null);
  const defaultCorr = watchlist.slice(0, 12).map((t) => t.symbol);
  const corrTickers = corrSel ?? defaultCorr;
  const corr = useFetch(
    () => get(`/correlation?tickers=${corrTickers.join(",")}`),
    [wlVersion, corrTickers.join(",")]
  );

  if (loading) return <Loading height={400} label="Computing risk metrics…" />;
  if (error) return <ErrorNote error={error} onRetry={reload} />;

  const toggleCorr = (sym) => {
    const next = corrTickers.includes(sym) ? corrTickers.filter((t) => t !== sym) : [...corrTickers, sym];
    if (next.length >= 2 && next.length <= 16) setCorrSel(next);
  };

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div variants={rise}>
        <h2 className="page-title">Risk profile</h2>
        <p className="page-sub">
          Know what each name can do to you before it does it. Colors flag how each stock scores on that metric.
        </p>
      </motion.div>

      <motion.div className="card" variants={rise}>
        <div className="card-title">Every watchlist ticker, quantified — click a row for its chart</div>
        <DataTable
          onRowClick={(r) => goChart(r.ticker)}
          initialSort={{ key: "sharpe", dir: -1 }}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <span className="tick">{r.ticker}</span> },
            { key: "beta", label: "Beta", tip: data.info.beta, render: (r) => <span style={{ color: LEVEL_COLOR[r.beta_level] }}>{fmtNum(r.beta)}</span> },
            { key: "down_beta", label: "Down-β", tip: data.info.down_beta, render: (r) => <span style={{ color: r.down_beta > 1.15 ? "var(--bad)" : r.down_beta < 0.8 ? "var(--good)" : undefined }}>{fmtNum(r.down_beta)}</span> },
            { key: "alpha", label: "Alpha/yr", tip: data.info.alpha, render: (r) => fmtPct(r.alpha * 100, 1), className: (r) => (r.alpha >= 0 ? "up mono" : "down mono") },
            { key: "sharpe", label: "Sharpe", tip: data.info.sharpe, render: (r) => <span style={{ color: LEVEL_COLOR[r.sharpe_level] }}>{fmtNum(r.sharpe)}</span> },
            { key: "calmar", label: "Calmar", tip: data.info.calmar, render: (r) => fmtNum(r.calmar) },
            { key: "volatility", label: "Volatility", tip: data.info.volatility, render: (r) => fmtPct(r.volatility * 100, 0, false) },
            { key: "var_95", label: "Bad-day loss", tip: data.info.var_95, render: (r) => fmtPct(r.var_95 * 100, 1, false) },
            { key: "cvar_95", label: "Tail loss", tip: data.info.cvar_95, render: (r) => fmtPct(r.cvar_95 * 100, 1, false), className: () => "down mono" },
            { key: "max_drawdown", label: "Worst drop", tip: data.info.max_drawdown, render: (r) => fmtPct(r.max_drawdown * 100, 0, false), className: () => "down mono" },
          ]}
          rows={data.rows}
        />
      </motion.div>

      <motion.div className="card" variants={rise}>
        <div className="card-title">Risk vs reward — where each name sits (bigger, greener = better risk-adjusted)</div>
        <RiskReturnScatter rows={data.rows} goChart={goChart} />
        <p className="note" style={{ marginBottom: 0 }}>
          Up and to the left is the sweet spot: more return for less risk. Bubble size and color track the Sharpe ratio.
        </p>
      </motion.div>

      <motion.div className="card" variants={rise}>
        <div className="card-title" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span>How risk evolved over time</span>
          <select className="field" style={{ padding: "5px 9px" }}
            value={detailTicker ?? data.rows[0]?.ticker ?? ""}
            onChange={(e) => setDetailTicker(e.target.value)}>
            {data.rows.map((r) => <option key={r.ticker} value={r.ticker}>{r.ticker}</option>)}
          </select>
        </div>
        {(detailTicker ?? data.rows[0]?.ticker) && <RiskDetail ticker={detailTicker ?? data.rows[0].ticker} />}
      </motion.div>

      <motion.div className="card" variants={rise}>
        <div className="card-title">
          Do they move together? <InfoTip text="Correlation of daily moves: +1 = always together (no diversification), 0 = unrelated, -1 = opposite. A portfolio of highly-correlated names is one bet, not several." />
        </div>
        <div className="wl-chips" style={{ flexWrap: "wrap", marginBottom: 12 }}>
          {watchlist.map((t) => {
            const on = corrTickers.includes(t.symbol);
            return (
              <button key={t.symbol} className="chip"
                style={{ cursor: "pointer", borderColor: on ? "var(--accent)" : undefined, color: on ? "var(--ink)" : "var(--muted)" }}
                onClick={() => toggleCorr(t.symbol)}>
                {t.symbol}
              </button>
            );
          })}
        </div>
        {corr.loading && <Loading height={220} />}
        {corr.data && <Heatmap tickers={corr.data.tickers} matrix={corr.data.matrix} />}
        <div className="legend" style={{ marginTop: 10 }}>
          <span><span className="sw" style={{ background: "#d03b3b" }} />move opposite</span>
          <span><span className="sw" style={{ background: "#383835" }} />unrelated</span>
          <span><span className="sw" style={{ background: "#3987e5" }} />move together</span>
        </div>
      </motion.div>
    </motion.div>
  );
}
