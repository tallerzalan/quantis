import { useState } from "react";
import { motion } from "framer-motion";
import { get, post, fmt$, fmtPct, fmtNum } from "../api";
import { useFetch, Verdict, Tile, ErrorNote, Loading, DataTable, ScoreRing, InfoTip, stagger, rise } from "../components/ui";
import { Sparkline } from "../components/charts";

export default function Ideas({ wlVersion, capital, goChart, notify }) {
  const { data, error, loading, reload } = useFetch(() => get(`/ideas?capital=${capital}`), [wlVersion, capital]);
  const [buying, setBuying] = useState(false);

  if (loading) return <Loading height={420} label="Scoring your watchlist…" />;
  if (error) return <ErrorNote error={error} onRetry={reload} />;

  const buyAll = async () => {
    setBuying(true);
    try {
      for (const i of data.ideas) await post("/portfolio/buy", { ticker: i.ticker, dollars: i.dollars, price: i.entry });
      notify(`Logged ${data.ideas.length} paper positions — see Portfolio.`);
    } catch (e) {
      notify(String(e.message || e), true);
    } finally { setBuying(false); }
  };

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div variants={rise} style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h2 className="page-title">Today's trade ideas</h2>
          <p className="page-sub">
            The best setups in your watchlist right now, sized for your {fmt$(capital, 0)}. Each has a stop-loss —
            the exit that caps a loss if it goes wrong. <Verdict v={data.regime} />
          </p>
        </div>
        <button className="btn" onClick={buyAll} disabled={buying}>
          {buying ? "Logging…" : "Paper-buy all 5"}
        </button>
      </motion.div>

      <div className="grid cols-2" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))" }}>
        {data.ideas.map((i, n) => (
          <motion.div key={i.ticker} className="card idea" variants={rise}>
            <div className="row1">
              <div>
                <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                  <button onClick={() => goChart(i.ticker)} style={{ all: "unset", cursor: "pointer" }}>
                    <span className="tick" style={{ fontSize: 18 }}>{i.ticker}</span>
                  </button>
                  <span className="dim" style={{ fontSize: 11.5 }}>{i.group}</span>
                </div>
                <div className="money" style={{ fontSize: 24 }}>{fmt$(i.entry)}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Sparkline points={i.spark} width={110} height={44} />
                <InfoTip text="Quantis Score: how good this setup ranks vs everything else in your watchlist, 0-100.">
                  <div><ScoreRing score={i.edge} size={62} /></div>
                </InfoTip>
              </div>
            </div>

            <div className="levels">
              <div>
                <div className="lb">Invest</div>
                <div className="lv money">{fmt$(i.dollars)}</div>
              </div>
              <div>
                <div className="lb">Stop (exit if hit)</div>
                <div className="lv down">{fmt$(i.stop)}</div>
              </div>
              <div>
                <div className="lb">Target</div>
                <div className="lv up">{fmt$(i.target)}</div>
              </div>
            </div>

            <div className="note">
              Hold ~{i.hold} days · risking {fmtNum(i.risk_pct, 1)}% ({fmt$((i.dollars * i.risk_pct) / 100)}) if the stop hits
            </div>
            <div style={{ fontSize: 12.5, lineHeight: 1.5 }}>{i.reason}</div>
          </motion.div>
        ))}
      </div>

      <motion.div className="card" variants={rise}>
        <div className="card-title">Full ranking — every watchlist ticker by Quantis Score</div>
        <DataTable
          onRowClick={(r) => goChart(r.ticker)}
          initialSort={{ key: "edge", dir: -1 }}
          columns={[
            { key: "ticker", label: "Ticker", render: (r) => <span className="tick">{r.ticker}</span> },
            { key: "edge", label: "Score", render: (r) => <b className="mono">{fmtNum(r.edge, 0)}</b> },
            { key: "momentum", label: "Momentum", tip: "How strongly it's been rising lately (z-score vs peers).", render: (r) => fmtNum(r.momentum) },
            { key: "trend", label: "Trend", tip: "Is it above its moving averages with momentum confirming?", render: (r) => fmtNum(r.trend) },
            { key: "meanrev", label: "Dip setup", tip: "Is it briefly oversold inside an uptrend (a buyable dip)?", render: (r) => fmtNum(r.meanrev) },
            { key: "volume", label: "Volume", tip: "Unusual trading activity vs its norm.", render: (r) => fmtNum(r.volume) },
            { key: "chg20", label: "20-day", render: (r) => fmtPct(r.chg20), className: (r) => (r.chg20 >= 0 ? "up mono" : "down mono") },
          ]}
          rows={data.ranked}
        />
      </motion.div>

      <p className="note">
        ⚠️ These maximize <i>expected</i> value — individual trades will lose, and that's normal. The stop caps each loss.
        Educational tool, not financial advice.
      </p>
    </motion.div>
  );
}
