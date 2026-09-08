import { motion } from "framer-motion";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Cell, ReferenceLine,
  PieChart, Pie, Tooltip as RTooltip,
} from "recharts";
import { get } from "../api";
import { useFetch, Loading, ErrorNote, DataTable, InfoTip, stagger, rise } from "../components/ui";
import { fmtNum, fmtPct } from "../api";

const SECTOR_COLORS = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)", "var(--s7)", "var(--s8)", "var(--muted)"];

function ChartTip({ active, payload, label, fmt }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--surface-3)", border: "1px solid var(--baseline)", borderRadius: 8, padding: "7px 10px", fontSize: 12 }}>
      <div style={{ color: "var(--ink)", fontWeight: 600 }}>{label ?? payload[0].name}</div>
      <div style={{ color: "var(--ink-2)" }}>{fmt ? fmt(payload[0].value) : payload[0].value}</div>
    </div>
  );
}

function FactorBars({ betas, labels }) {
  const data = Object.entries(betas || {})
    .map(([k, v]) => ({ name: labels?.[k] || k, beta: v }))
    .sort((a, b) => Math.abs(b.beta) - Math.abs(a.beta));
  if (!data.length) return <div className="note">No factor data.</div>;
  return (
    <ResponsiveContainer width="100%" height={Math.max(180, data.length * 42)}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 24, top: 4, bottom: 4 }}>
        <XAxis type="number" tick={{ fill: "var(--muted)", fontSize: 11 }} axisLine={{ stroke: "var(--line)" }} tickLine={false} />
        <YAxis type="category" dataKey="name" width={92} tick={{ fill: "var(--ink-2)", fontSize: 12 }} axisLine={false} tickLine={false} />
        <ReferenceLine x={0} stroke="var(--baseline)" />
        <RTooltip cursor={{ fill: "var(--surface-2)" }} content={<ChartTip fmt={(v) => `beta ${fmtNum(v, 2)}`} />} />
        <Bar dataKey="beta" radius={[0, 4, 4, 0]} barSize={18}>
          {data.map((d, i) => <Cell key={i} fill={d.beta >= 0 ? "var(--accent)" : "var(--down)"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function SectorDonut({ sectors }) {
  const data = (sectors || []).map((s) => ({ name: s.sector, value: s.weight }));
  if (!data.length) return <div className="note">No sector data.</div>;
  return (
    <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 16, alignItems: "center" }}>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" innerRadius={48} outerRadius={80} paddingAngle={2} stroke="var(--bg)" strokeWidth={2}>
            {data.map((d, i) => <Cell key={i} fill={SECTOR_COLORS[i % SECTOR_COLORS.length]} />)}
          </Pie>
          <RTooltip content={<ChartTip fmt={(v) => `${(v * 100).toFixed(1)}%`} />} />
        </PieChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {data.map((d, i) => (
          <div key={d.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
            <span style={{ width: 10, height: 10, borderRadius: 3, background: SECTOR_COLORS[i % SECTOR_COLORS.length], flexShrink: 0 }} />
            <span style={{ flex: 1, color: "var(--ink-2)" }}>{d.name}</span>
            <span className="mono" style={{ color: "var(--ink)" }}>{(d.value * 100).toFixed(1)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Factors({ wlVersion, goChart }) {
  const { data, error, loading, retry } = useFetch(() => get("/factors"), [wlVersion]);

  const factorCols = data ? data.factors.map((f) => ({
    key: f, label: data.labels?.[f] || f, tip: `Beta to the ${(data.labels?.[f] || f).toLowerCase()} factor.`,
    render: (r) => <span className="mono" style={{ color: Math.abs(r.betas?.[f] ?? 0) > 0.3 ? "var(--ink)" : "var(--muted)" }}>{fmtNum(r.betas?.[f], 2)}</span>,
  })) : [];

  const columns = data ? [
    { key: "ticker", label: "Ticker", render: (r) => <span className="tick clickable" onClick={() => goChart(r.ticker)}>{r.ticker}</span> },
    ...factorCols,
    { key: "r2", label: "R²", tip: data.info?.r2, render: (r) => <span className="mono">{fmtPct(r.r2 * 100, 0, false)}</span> },
    { key: "alpha", label: "Alpha", tip: "Annualized return not explained by the factors.", render: (r) => <span className="mono" style={{ color: r.alpha >= 0 ? "var(--up)" : "var(--down)" }}>{fmtPct(r.alpha * 100, 0)}</span> },
  ] : [];

  return (
    <motion.div className="page" variants={stagger} initial="hidden" animate="show">
      <motion.div variants={rise}>
        <h1 className="page-title">Factors &amp; sectors</h1>
        <div className="page-sub">What actually drives your watchlist — the style tilts and sector bets underneath the tickers.</div>
      </motion.div>

      {loading && <Loading height={200} label="Regressing your watchlist against the factors…" />}
      {error && <ErrorNote error={error} onRetry={retry} />}

      {data && (
        <>
          <motion.div className="grid cols-2" variants={rise}>
            <div className="card">
              <div className="card-title">Watchlist factor exposure</div>
              <FactorBars betas={data.portfolio?.betas} labels={data.labels} />
              <div className="explain" style={{ marginTop: 12 }}>{data.portfolio?.summary}</div>
            </div>
            <div className="card">
              <div className="card-title">Sector allocation (equal-weight)</div>
              <SectorDonut sectors={data.sectors} />
              <div className="explain" style={{ marginTop: 12 }}>{data.sector_summary}</div>
            </div>
          </motion.div>

          <motion.div className="card" variants={rise}>
            <div className="card-title">
              Per-ticker factor betas
              <InfoTip text="Each number is how strongly the stock moves with that factor. ~1 = full exposure; near 0 = none; negative = moves opposite." >
                <span> </span>
              </InfoTip>
            </div>
            <DataTable columns={columns} rows={data.rows} initialSort={{ key: "r2", dir: -1 }} />
          </motion.div>
        </>
      )}
    </motion.div>
  );
}
