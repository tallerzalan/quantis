import { useState } from "react";
import { motion } from "framer-motion";
import { get, post, fmt$, fmtPct, fmtNum } from "../api";
import { useFetch, Verdict, Explain, Tile, ErrorNote, Loading, DataTable, Ticker, stagger, rise } from "../components/ui";

export default function Portfolio({ wlVersion, watchlist, notify }) {
  const { data, error, loading, reload } = useFetch(() => get("/portfolio"), [wlVersion]);
  const [form, setForm] = useState({ ticker: "", dollars: 20 });
  const [busy, setBusy] = useState(false);

  if (loading) return <Loading height={400} label="Valuing your positions…" />;
  if (error) return <ErrorNote error={error} onRetry={reload} />;

  const act = async (fn) => {
    setBusy(true);
    try { await fn(); reload(); }
    catch (e) { notify(String(e.message || e), true); }
    finally { setBusy(false); }
  };

  const buy = () => act(async () => {
    if (!form.ticker) throw new Error("Pick a ticker first.");
    await post("/portfolio/buy", { ticker: form.ticker, dollars: Number(form.dollars) });
    notify(`Bought ${fmt$(Number(form.dollars))} of ${form.ticker} (paper).`);
  });

  const pnl = data.total - data.start;

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div className="hero" variants={rise}>
        <div style={{ position: "relative" }}>
          <div className="card-title">Paper portfolio — practice with zero risk</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
            <span style={{ fontFamily: "var(--display)", fontSize: 40, fontWeight: 600, color: "var(--ink)", fontVariantNumeric: "tabular-nums" }}>
              <Ticker value={data.total} format={(v) => fmt$(v)} />
            </span>
            <span className={`mono ${pnl >= 0 ? "up" : "down"}`} style={{ fontSize: 16 }}>
              {pnl >= 0 ? "▲" : "▼"} {fmt$(Math.abs(pnl))} since ${data.start.toFixed(0)} start
            </span>
          </div>
          <div className="note" style={{ marginTop: 6 }}>Cash available: {fmt$(data.cash)}</div>
          {data.var_sentence && <p style={{ fontSize: 13, marginBottom: 0, marginTop: 12, position: "relative" }}>{data.var_sentence}</p>}
        </div>
        <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 8, justifyContent: "center" }}>
          {data.verdicts ? (
            <>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <Verdict v={data.verdicts.beta} />
                <Verdict v={data.verdicts.sharpe} />
                <Verdict v={data.verdicts.alpha} />
              </div>
              <Explain v={data.verdicts.beta} />
            </>
          ) : (
            <p className="note">Buy something (paper money!) and portfolio-level beta, alpha and risk appear here.</p>
          )}
        </div>
      </motion.div>

      <motion.div className="card pad-sm" variants={rise}>
        <div className="controls">
          <label className="field">Ticker
            <select value={form.ticker} onChange={(e) => setForm((f) => ({ ...f, ticker: e.target.value }))}>
              <option value="">Choose…</option>
              {watchlist.map((t) => <option key={t.symbol} value={t.symbol}>{t.symbol}</option>)}
            </select>
          </label>
          <label className="field">Dollars
            <input type="number" min="1" step="1" value={form.dollars}
              onChange={(e) => setForm((f) => ({ ...f, dollars: e.target.value }))} />
          </label>
          <button className="btn" onClick={buy} disabled={busy}>Buy (paper)</button>
          <button className="btn danger sm" onClick={() => act(async () => { await post("/portfolio/reset"); notify("Portfolio reset to $100 cash."); })}>
            Reset to $100
          </button>
        </div>
      </motion.div>

      {data.positions.length > 0 && (
        <motion.div className="card" variants={rise}>
          <div className="card-title">Positions — marked to the latest price</div>
          <DataTable
            initialSort={{ key: "value", dir: -1 }}
            columns={[
              { key: "ticker", label: "Ticker", render: (r) => <span className="tick">{r.ticker}</span> },
              { key: "shares", label: "Shares", render: (r) => fmtNum(r.shares, 4) },
              { key: "cost", label: "Avg cost", render: (r) => fmt$(r.cost) },
              { key: "last", label: "Now", render: (r) => fmt$(r.last) },
              { key: "value", label: "Value", render: (r) => fmt$(r.value) },
              { key: "pnl", label: "P&L", render: (r) => fmt$(r.pnl), className: (r) => (r.pnl >= 0 ? "up mono" : "down mono") },
              { key: "pnl_pct", label: "P&L %", render: (r) => fmtPct(r.pnl_pct), className: (r) => (r.pnl_pct >= 0 ? "up mono" : "down mono") },
              {
                key: "actions", label: "", render: (r) => (
                  <button className="btn ghost sm" onClick={(e) => { e.stopPropagation(); act(async () => { await post("/portfolio/sell", { ticker: r.ticker }); notify(`Sold ${r.ticker} at market.`); }); }}>
                    Sell
                  </button>
                ),
              },
            ]}
            rows={data.positions}
          />
        </motion.div>
      )}

      {data.metrics && (
        <div className="grid cols-4">
          <motion.div variants={rise}><Tile label="Portfolio beta" tip="How hard the market's moves hit your whole portfolio." value={fmtNum(data.metrics.beta)} /></motion.div>
          <motion.div variants={rise}><Tile label="Portfolio alpha" tip="Yearly return beyond market exposure." value={fmtPct((data.metrics.alpha ?? 0) * 100, 1)} /></motion.div>
          <motion.div variants={rise}><Tile label="Volatility" tip="Yearly swing size of your mix." value={fmtPct((data.metrics.volatility ?? 0) * 100, 0, false)} /></motion.div>
          <motion.div variants={rise}><Tile label="Worst drop" tip="Biggest fall this mix suffered in the last year." value={fmtPct((data.metrics.max_drawdown ?? 0) * 100, 0, false)} /></motion.div>
        </div>
      )}
    </motion.div>
  );
}
