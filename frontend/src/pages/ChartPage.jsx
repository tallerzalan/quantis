import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { get, fmt$, fmtPct, fmtNum } from "../api";
import { useFetch, Verdict, Explain, Tile, ErrorNote, Loading, stagger, rise } from "../components/ui";
import { CandleChart } from "../components/charts";
import { SearchBox } from "../components/TopBar";

const PERIODS = ["3mo", "6mo", "1y", "2y", "5y"];
const TOGGLES = [
  { key: "bb", label: "Bollinger", tip: "20-day ±2σ envelope: the stock's statistically 'normal' range." },
  { key: "rsi", label: "RSI", tip: "Momentum 0–100. Under 30 = oversold (dip), over 70 = overbought." },
  { key: "macd", label: "MACD", tip: "Trend momentum: bars above zero = bullish push, below = bearish." },
];

function EventCard({ ev }) {
  return (
    <div>
      <div className="event-head">
        <span className="mono dim">{ev.date}</span>
        <span className={`mono ${ev.direction === "up" ? "up" : "down"}`}>{ev.title}</span>
        <span className="chip">{ev.catalyst_label}</span>
        {ev.rvol >= 2 && <span className="chip">{ev.rvol.toFixed(1)}× volume</span>}
      </div>
      <div className="event-story">{ev.story}</div>
      {ev.headlines?.length > 0 && (
        <div className="event-links">
          {ev.headlines.map((h, i) =>
            h.url ? (
              <a key={i} href={h.url} target="_blank" rel="noreferrer">{h.title}{h.publisher ? ` — ${h.publisher}` : ""}</a>
            ) : (
              <span key={i} className="dim">{h.title}</span>
            )
          )}
        </div>
      )}
    </div>
  );
}

export default function ChartPage({ wlVersion, ticker, setTicker, watchlist, onAddToWatchlist }) {
  const [period, setPeriod] = useState("1y");
  const [show, setShow] = useState({ bb: false, rsi: true, macd: false });
  const [hoverEv, setHoverEv] = useState(null);
  const [pinnedDate, setPinnedDate] = useState(null);
  const { data, error, loading, reload } = useFetch(
    () => get(`/chart/${ticker}?period=${period}`),
    [ticker, period, wlVersion]
  );
  const events = useFetch(() => get(`/events/${ticker}?period=${period}`), [ticker, period]);
  const facts = useFetch(() => get(`/facts/${ticker}`), [ticker]);

  const evByDate = useMemo(() => {
    const m = {};
    for (const ev of events.data?.events ?? []) m[ev.date] = ev;
    return m;
  }, [events.data]);
  const evList = events.data?.events ?? [];
  const pinned = evList.find((e) => e.date === pinnedDate) ?? null;

  const onCrosshair = (time) => {
    const ev = time ? evByDate[time] ?? null : null;
    setHoverEv((prev) => (prev?.date === ev?.date ? prev : ev));
  };

  const chartHeight = 380 + (show.rsi ? 85 : 0) + (show.macd ? 85 : 0);

  return (
    <motion.div className="page" variants={stagger} initial="initial" animate="animate">
      <motion.div variants={rise} style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <h2 className="page-title" style={{ marginRight: 4 }}>Price explorer</h2>
        <SearchBox onPick={(sym) => setTicker(sym)} placeholder="Chart any ticker…" />
        <div className="seg">
          {PERIODS.map((p) => (
            <button key={p} className={p === period ? "on" : ""} onClick={() => setPeriod(p)}>{p}</button>
          ))}
        </div>
        <div className="seg">
          {TOGGLES.map((t) => (
            <button key={t.key} className={show[t.key] ? "on" : ""} title={t.tip}
              onClick={() => setShow((s) => ({ ...s, [t.key]: !s[t.key] }))}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="wl-chips" style={{ maxWidth: 380 }}>
          {watchlist.slice(0, 12).map((t) => (
            <button key={t.symbol} className="chip" style={{ cursor: "pointer", borderColor: t.symbol === ticker ? "var(--accent)" : undefined }}
              onClick={() => setTicker(t.symbol)}>
              {t.symbol}
            </button>
          ))}
        </div>
      </motion.div>

      {loading && <Loading height={420} label={`Loading ${ticker}…`} />}
      {error && <ErrorNote error={error} onRetry={reload} />}

      {data && !loading && (
        <>
          <motion.div className="card" variants={rise}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                <span className="tick" style={{ fontSize: 22 }}>{data.ticker}</span>
                <span className="money" style={{ fontSize: 24 }}>{fmt$(data.candles.at(-1)?.close)}</span>
                <span className={`mono ${data.metrics.chg1 >= 0 ? "up" : "down"}`}>{fmtPct(data.metrics.chg1)} today</span>
                <span className={`mono ${data.metrics.total_period >= 0 ? "up" : "down"}`}>{fmtPct(data.metrics.total_period)} over {period}</span>
              </div>
              <div className="legend">
                <span><span className="sw" style={{ background: "#c98500" }} />20-day avg</span>
                <span><span className="sw" style={{ background: "#9085e9" }} />50-day avg</span>
                {show.bb && <span><span className="sw" style={{ background: "rgba(137,135,129,0.55)" }} />±2σ bands</span>}
                <span><span className="sw" style={{ background: "rgba(57,135,229,0.9)" }} />unusual volume</span>
                {!data.in_watchlist && (
                  <button className="btn ghost sm" onClick={() => onAddToWatchlist(data.ticker)}>+ Add to watchlist</button>
                )}
              </div>
            </div>
            <div style={{ position: "relative" }}>
              <CandleChart
                candles={data.candles}
                ema20={data.ema20} ema50={data.ema50}
                bb={show.bb ? { upper: data.bb_upper, lower: data.bb_lower, mid: data.bb_mid } : null}
                volMa={data.vol_ma}
                markers={events.data?.markers}
                rsi={show.rsi ? data.rsi14 : null}
                macd={show.macd ? { line: data.macd_line, signal: data.macd_signal, hist: data.macd_hist } : null}
                onCrosshair={onCrosshair}
                height={chartHeight}
              />
              {hoverEv && (
                <div className="fan-tip" style={{ right: 76, top: 10, maxWidth: 360 }}>
                  <EventCard ev={hoverEv} />
                </div>
              )}
            </div>
            {data.readouts && (
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                <Verdict v={data.readouts.rsi} />
                <Verdict v={data.readouts.macd} />
                <Verdict v={data.readouts.bollinger} />
                <Verdict v={data.readouts.volume} />
                <span className="dim" style={{ fontSize: 12, alignSelf: "center" }}>hover a chip for what it means · hover an arrow on the chart for why it moved</span>
              </div>
            )}
          </motion.div>

          {evList.length > 0 && (
            <motion.div className="card" variants={rise}>
              <div className="card-title">Why it moved — statistically significant days</div>
              <div className="event-strip">
                {evList.map((ev) => (
                  <button key={ev.date}
                    className={`chip evchip ${ev.direction === "up" ? "up" : "down"} ${pinnedDate === ev.date ? "on" : ""}`}
                    onClick={() => setPinnedDate(pinnedDate === ev.date ? null : ev.date)}
                    onMouseEnter={() => setHoverEv(ev)} onMouseLeave={() => setHoverEv(null)}>
                    {ev.date.slice(5)} · {fmtPct(ev.ret * 100, 1)}
                  </button>
                ))}
              </div>
              {pinned
                ? <div style={{ marginTop: 12 }}><EventCard ev={pinned} /></div>
                : <div className="dim" style={{ fontSize: 12, marginTop: 10 }}>
                    Hover the arrows on the chart (or the chips above) for the story behind each move; click a chip to pin it here.
                  </div>}
              <div className="dim" style={{ fontSize: 12, marginTop: 10 }}>{events.data.note}</div>
            </motion.div>
          )}

          <div className="grid cols-2" style={{ alignItems: "start" }}>
            <motion.div className="card" variants={rise}>
              <div className="card-title">Fact sheet{facts.data?.name ? ` — ${facts.data.name}` : ""}</div>
              {facts.loading && <Loading height={120} />}
              {facts.data?.sheet?.length > 0 ? (
                <div className="facts">
                  {facts.data.sheet.map((r) => (
                    <div key={r.label} className="facts-row">
                      <span className="dim">{r.label}</span>
                      <span className="money" style={{ fontSize: 14 }}>{r.value}</span>
                      <span className="facts-note">{r.note}</span>
                    </div>
                  ))}
                </div>
              ) : (!facts.loading && <div className="dim" style={{ fontSize: 13 }}>No profile data available for {ticker}.</div>)}
              {facts.data?.vol_line && <div className="facts-note" style={{ marginTop: 10 }}>{facts.data.vol_line}</div>}
              {facts.data?.next_earnings && (
                <div className="facts-note" style={{ marginTop: 6 }}>
                  Next earnings: <span className="mono">{facts.data.next_earnings}</span> — expect a jump in either direction around that date.
                </div>
              )}
            </motion.div>

            <motion.div variants={rise} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="grid cols-2">
                <Tile label="Beta vs market" tip="How much it moves when the S&P 500 moves. 2.0 = twice the swings." value={fmtNum(data.metrics.beta)} sub={<Verdict v={data.verdicts.beta} />} />
                <Tile label="Alpha / yr" tip="Return beyond what market exposure explains. Positive = genuine outperformance." value={data.metrics.alpha == null ? "—" : fmtPct(data.metrics.alpha * 100, 1)} sub={<Verdict v={data.verdicts.alpha} />} />
                <Tile label="Sharpe" tip="Return per unit of risk. Above 1 is good." value={fmtNum(data.metrics.sharpe)} sub={<Verdict v={data.verdicts.sharpe} />} />
                <Tile label="Worst drop" tip="Biggest peak-to-trough fall in this window." value={data.metrics.max_drawdown == null ? "—" : fmtPct(data.metrics.max_drawdown * 100, 0, false)} sub={<Verdict v={data.verdicts.drawdown} />} />
              </div>
              <div className="card pad-sm">
                <div className="card-title">What the signals say right now</div>
                <Explain v={data.readouts?.rsi} />
                <Explain v={data.readouts?.macd} />
                <Explain v={data.readouts?.bollinger} />
                <Explain v={data.readouts?.volume} />
              </div>
            </motion.div>
          </div>

          <motion.div className="card pad-sm" variants={rise}>
            <div className="card-title">What the risk numbers mean</div>
            <Explain v={data.verdicts.beta} />
            <Explain v={data.verdicts.sharpe} />
            <Explain v={data.verdicts.drawdown} />
          </motion.div>
        </>
      )}
    </motion.div>
  );
}
