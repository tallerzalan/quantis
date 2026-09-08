import { motion } from "framer-motion";
import { get, fmt$, fmtPct, fmtNum } from "../api";
import { useFetch, Verdict, ErrorNote, Loading, DataTable, stagger, rise } from "../components/ui";
import { MagicCard } from "../components/ui/magic-card";
import { BorderBeam } from "../components/ui/border-beam";
import { NumberTicker } from "../components/ui/number-ticker";

export default function Today({ wlVersion, goChart }) {
  const { data, error, loading, reload } = useFetch(() => get("/market"), [wlVersion]);

  if (loading) return <Loading height={420} label="Pulling live market data…" />;
  if (error) return <ErrorNote error={error} onRetry={reload} />;

  const { regime, indices, rows, missing } = data;
  const movers = [...rows].filter((r) => r.chg1 != null).sort((a, b) => Math.abs(b.chg1) - Math.abs(a.chg1)).slice(0, 4);
  const scored = rows.filter((r) => r.edge != null);
  const avgScore = scored.length ? scored.reduce((s, r) => s + r.edge, 0) / scored.length : 0;
  const with20 = rows.filter((r) => r.chg20 != null);
  const breadth = with20.length ? with20.filter((r) => r.chg20 > 0).length / with20.length : 0;
  const leaders = scored.filter((r) => r.edge >= 80).length;

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <div className="bento">
        {/* ---- hero ---- */}
        <MagicCard
          className="col-2 row-2 hero-card"
          gradientFrom="var(--accent)" gradientTo="var(--accent-2)"
          gradientColor="rgba(10,132,255,0.18)" gradientOpacity={0.5} gradientSize={280}>
          <BorderBeam size={120} duration={9} colorFrom="var(--accent)" colorTo="var(--accent-2)" />
          <div className="hero-inner">
            <div className="hero-top">
              <Verdict v={regime} />
              <span className="note">live · {data.as_of ? data.as_of.slice(0, 10) : "today"}</span>
            </div>
            <h1 className="hero-headline">{regime.detail}</h1>
            <div className="hero-indices">
              {indices.map((ix) => (
                <button key={ix.ticker} className="ix" onClick={() => goChart(ix.ticker)}>
                  <span className="tick" style={{ fontSize: 12 }}>{ix.ticker}</span>
                  <span className="money" style={{ fontSize: 19 }}>
                    ${<NumberTicker value={ix.last} decimalPlaces={2} className="money" />}
                  </span>
                  <span className={`mono ${ix.chg >= 0 ? "up" : "down"}`} style={{ fontSize: 12.5 }}>{fmtPct(ix.chg)}</span>
                </button>
              ))}
            </div>
            <div className="hero-stats">
              <div><div className="hs-val"><NumberTicker value={Math.round(breadth * 100)} />%</div><div className="hs-lbl">above 20-day avg</div></div>
              <div><div className="hs-val"><NumberTicker value={Math.round(avgScore)} /></div><div className="hs-lbl">avg Quantis Score</div></div>
              <div><div className="hs-val"><NumberTicker value={leaders} /></div><div className="hs-lbl">setups scoring 80+</div></div>
            </div>
          </div>
        </MagicCard>

        {/* ---- movers ---- */}
        <div className="card col-2">
          <div className="card-title">Biggest movers today</div>
          <div className="movers">
            {movers.map((m) => (
              <button key={m.ticker} className="mover" onClick={() => goChart(m.ticker)}>
                <span className="tick">{m.ticker}</span>
                <span className="dim" style={{ flex: 1, fontSize: 12 }}>{m.group}</span>
                <span className={`mono ${m.chg1 >= 0 ? "up" : "down"}`} style={{ fontWeight: 600 }}>{fmtPct(m.chg1)}</span>
              </button>
            ))}
          </div>
        </div>

        {/* ---- breadth bar ---- */}
        <div className="card col-2">
          <div className="card-title">Market breadth</div>
          <div className="breadth">
            <div className="breadth-num"><NumberTicker value={Math.round(breadth * 100)} />%</div>
            <div className="breadth-sub">of your {with20.length} tracked names are trading above their 20-day average.</div>
            <div className="breadth-track"><motion.div className="breadth-fill"
              initial={{ width: 0 }} animate={{ width: `${breadth * 100}%` }} transition={{ duration: 0.9, ease: [0.2, 0.7, 0.2, 1] }} /></div>
          </div>
        </div>
      </div>

      {missing?.length > 0 && (
        <div className="note">No data found for: {missing.join(", ")} — remove them or check the symbols.</div>
      )}

      <motion.div className="card" variants={rise}>
        <div className="card-title">Your watchlist — click any row to open its chart</div>
        <DataTable
          onRowClick={(r) => goChart(r.ticker)}
          initialSort={{ key: "edge", dir: -1 }}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <span className="tick">{r.ticker}</span> },
            { key: "last", label: "Price", render: (r) => fmt$(r.last) },
            { key: "chg1", label: "Today", tip: "Change vs yesterday's close.", render: (r) => fmtPct(r.chg1), className: (r) => (r.chg1 >= 0 ? "up mono" : "down mono") },
            { key: "chg5", label: "5 days", render: (r) => fmtPct(r.chg5), className: (r) => (r.chg5 >= 0 ? "up mono" : "down mono") },
            { key: "chg20", label: "20 days", render: (r) => fmtPct(r.chg20), className: (r) => (r.chg20 >= 0 ? "up mono" : "down mono") },
            { key: "rsi14", label: "RSI-14", tip: "Under ~30 = oversold, over ~70 = overheated.", render: (r) => fmtNum(r.rsi14, 0) },
            { key: "rvol", label: "Volume", tip: "Today's volume vs the 20-day average. 2x+ means unusual attention.", render: (r) => (r.rvol == null ? "—" : `${r.rvol.toFixed(1)}×`) },
            { key: "edge", label: "Score", tip: "Composite 0-100 rank: momentum + trend + dip setup + volume. Higher = better setup right now.", render: (r) => <ScoreCell v={r.edge} /> },
            { key: "group", label: "Group", render: (r) => <span className="dim" style={{ fontSize: 11.5 }}>{r.group}</span> },
          ]}
          rows={rows}
        />
      </motion.div>
    </motion.div>
  );
}

function ScoreCell({ v }) {
  if (v == null) return <span className="dim">—</span>;
  const c = v >= 80 ? "var(--great)" : v >= 60 ? "var(--good)" : v >= 40 ? "var(--ok)" : "var(--muted)";
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 8, justifyContent: "flex-end" }}>
      <span style={{ width: 34, height: 4, borderRadius: 99, background: "var(--surface-3)", overflow: "hidden", display: "inline-block" }}>
        <span style={{ display: "block", height: "100%", width: `${v}%`, background: c }} />
      </span>
      <b className="mono" style={{ color: c, minWidth: 22, textAlign: "right" }}>{Math.round(v)}</b>
    </span>
  );
}
