import { useEffect, useRef, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  LineSeries,
  AreaSeries,
  HistogramSeries,
} from "lightweight-charts";

const BASE_OPTS = {
  layout: {
    background: { color: "transparent" },
    textColor: "#898781",
    fontFamily: '"Inter", system-ui, sans-serif',
    attributionLogo: false,
  },
  grid: {
    vertLines: { color: "#232322" },
    horzLines: { color: "#232322" },
  },
  rightPriceScale: { borderColor: "#383835" },
  timeScale: { borderColor: "#383835" },
  crosshair: {
    vertLine: { color: "#52514e", labelBackgroundColor: "#2a2a28" },
    horzLine: { color: "#52514e", labelBackgroundColor: "#2a2a28" },
  },
  autoSize: true,
};

function useLwChart(build, deps, height) {
  const ref = useRef(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, { ...BASE_OPTS, height });
    build(chart);
    chart.timeScale().fitContent();
    return () => chart.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return ref;
}

const timeStr = (t) =>
  typeof t === "string" ? t
    : t ? `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}` : null;

/* Candlestick + EMA/Bollinger overlays + volume (bright bars = unusual
   volume, >=2x normal) + optional RSI and MACD panes. Blue up / red down
   (CVD-safe). markers: significant-move arrows; onCrosshair(dateStr, point)
   fires as the cursor moves so pages can pop event explanations. */
export function CandleChart({ candles, ema20, ema50, bb, volMa, markers, rsi, macd, onCrosshair, height = 380 }) {
  const cbRef = useRef(null);
  cbRef.current = onCrosshair;
  const ref = useLwChart(
    (chart) => {
      const candle = chart.addSeries(CandlestickSeries, {
        upColor: "#3987e5",
        downColor: "#e66767",
        borderVisible: false,
        wickUpColor: "#3987e5",
        wickDownColor: "#e66767",
      });
      candle.setData(candles);
      if (markers?.length) createSeriesMarkers(candle, markers);

      const vol = chart.addSeries(HistogramSeries, {
        priceScaleId: "vol",
        priceFormat: { type: "volume" },
        color: "#383835",
        lastValueVisible: false,
      });
      vol.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
      vol.setData(candles.map((c) => {
        const up = c.close >= c.open, hot = c.rvol >= 2;
        return {
          time: c.time, value: c.volume,
          color: hot ? (up ? "rgba(57,135,229,0.9)" : "rgba(230,103,103,0.85)")
                     : (up ? "rgba(57,135,229,0.35)" : "rgba(230,103,103,0.30)"),
        };
      }));
      if (volMa?.length)
        chart.addSeries(LineSeries, { priceScaleId: "vol", color: "#6b6a64", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }).setData(volMa);

      if (bb?.upper?.length) {
        const bbOpts = { color: "rgba(137,135,129,0.55)", lineWidth: 1, priceLineVisible: false, lastValueVisible: false };
        chart.addSeries(LineSeries, bbOpts).setData(bb.upper);
        chart.addSeries(LineSeries, bbOpts).setData(bb.lower);
        chart.addSeries(LineSeries, { ...bbOpts, lineStyle: 2 }).setData(bb.mid);
      }
      if (ema20?.length)
        chart.addSeries(LineSeries, { color: "#c98500", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }).setData(ema20);
      if (ema50?.length)
        chart.addSeries(LineSeries, { color: "#9085e9", lineWidth: 2, priceLineVisible: false, lastValueVisible: false }).setData(ema50);

      let pane = 1;
      if (rsi?.length) {
        const r = chart.addSeries(LineSeries, {
          color: "#d55181", lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
          autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }),
        }, pane);
        r.setData(rsi);
        for (const price of [30, 70])
          r.createPriceLine({ price, color: "#52514e", lineWidth: 1, lineStyle: 3, axisLabelVisible: false });
        chart.panes()[pane]?.setHeight(85);
        pane += 1;
      }
      if (macd?.hist?.length) {
        const h = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
        h.setData(macd.hist.map((p) => ({ ...p, color: p.value >= 0 ? "rgba(57,135,229,0.6)" : "rgba(230,103,103,0.55)" })));
        chart.addSeries(LineSeries, { color: "#3987e5", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, pane).setData(macd.line);
        chart.addSeries(LineSeries, { color: "#c98500", lineWidth: 1, priceLineVisible: false, lastValueVisible: false }, pane).setData(macd.signal);
        chart.panes()[pane]?.setHeight(85);
      }

      chart.subscribeCrosshairMove((param) => {
        cbRef.current?.(param.time ? timeStr(param.time) : null, param.point ?? null);
      });
    },
    [candles, ema20, ema50, bb, volMa, markers, rsi, macd],
    height
  );
  return <div ref={ref} className="chart-box" style={{ height }} />;
}

/* Strategy vs benchmark equity curves. */
export function EquityChart({ equity, bench, names = ["Strategy", "SPY buy & hold"], height = 320 }) {
  const ref = useLwChart(
    (chart) => {
      const a = chart.addSeries(AreaSeries, {
        lineColor: "#3987e5",
        topColor: "rgba(57,135,229,0.25)",
        bottomColor: "rgba(57,135,229,0.02)",
        lineWidth: 2,
      });
      a.setData(equity);
      if (bench?.length) {
        const b = chart.addSeries(LineSeries, { color: "#008300", lineWidth: 2, priceLineVisible: false });
        b.setData(bench);
      }
    },
    [equity, bench],
    height
  );
  return (
    <div>
      <div className="legend" style={{ marginBottom: 6 }}>
        <span><span className="sw" style={{ background: "#3987e5" }} />{names[0]}</span>
        {bench?.length ? <span><span className="sw" style={{ background: "#008300" }} />{names[1]}</span> : null}
      </div>
      <div ref={ref} className="chart-box" style={{ height }} />
    </div>
  );
}

/* Tiny inline sparkline (SVG). */
export function Sparkline({ points, width = 150, height = 40 }) {
  if (!points?.length) return null;
  const vals = points.map((p) => p.value);
  const min = Math.min(...vals), max = Math.max(...vals);
  const span = max - min || 1;
  const xs = vals.map((v, i) => [
    (i / (vals.length - 1)) * (width - 2) + 1,
    height - 3 - ((v - min) / span) * (height - 6),
  ]);
  const d = xs.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const upward = vals[vals.length - 1] >= vals[0];
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={d} fill="none" stroke={upward ? "var(--up)" : "var(--down)"} strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

/* Monte Carlo fan: history (neutral ink) + one-hue uncertainty bands +
   median. Single entity, so bands encode confidence with opacity steps of
   the accent hue — never separate hues. Hover shows the percentile spread. */
export function FanChart({ history, fan, height = 340 }) {
  const boxRef = useRef(null);
  const [width, setWidth] = useState(760);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    if (!boxRef.current) return;
    const ro = new ResizeObserver((es) => setWidth(Math.max(320, es[0].contentRect.width)));
    ro.observe(boxRef.current);
    return () => ro.disconnect();
  }, []);

  if (!history?.length || !fan?.length) return null;
  const PAD = { l: 8, r: 74, t: 12, b: 24 };
  const W = width, H = height;
  const n = history.length + fan.length - 1; // fan[0] is today = last history point
  const lo = Math.min(...history.map((p) => p.value), ...fan.map((f) => f.p05));
  const hi = Math.max(...history.map((p) => p.value), ...fan.map((f) => f.p95));
  const pad = (hi - lo) * 0.05 || 1;
  const y = (v) => PAD.t + (H - PAD.t - PAD.b) * (1 - (v - lo + pad) / (hi - lo + 2 * pad));
  const x = (i) => PAD.l + (W - PAD.l - PAD.r) * (i / (n - 1));
  const splitI = history.length - 1;

  const histPath = history.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const fx = (j) => x(splitI + j);
  const band = (upKey, loKey) =>
    fan.map((f, j) => `${j ? "L" : "M"}${fx(j).toFixed(1)},${y(f[upKey]).toFixed(1)}`).join(" ") +
    [...fan].reverse().map((f, k) => `L${fx(fan.length - 1 - k).toFixed(1)},${y(f[loKey]).toFixed(1)}`).join(" ") + "Z";
  const median = fan.map((f, j) => `${j ? "L" : "M"}${fx(j).toFixed(1)},${y(f.p50).toFixed(1)}`).join(" ");

  const gridVals = [0.25, 0.5, 0.75].map((t) => lo + (hi - lo) * t);
  const fmt = (v) => v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(v < 20 ? 2 : v < 100 ? 1 : 0)}`;

  const onMove = (e) => {
    const rect = boxRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const i = Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (n - 1));
    if (i < 0 || i > n - 1) return setHover(null);
    setHover(i);
  };
  const hv = hover == null ? null
    : hover <= splitI
      ? { x: x(hover), time: history[hover].time, rows: [["price", history[hover].value]] }
      : {
          x: x(hover), time: fan[hover - splitI].time,
          rows: [["top 5%", fan[hover - splitI].p95], ["median", fan[hover - splitI].p50], ["worst 5%", fan[hover - splitI].p05]],
        };

  return (
    <div ref={boxRef} style={{ position: "relative" }} onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
      <svg width={W} height={H} role="img" aria-label="Simulated price range fan chart">
        {gridVals.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--line)" strokeWidth="1" />
            <text x={W - PAD.r + 6} y={y(v) + 3} fill="var(--muted)" fontSize="10" fontFamily="var(--mono)">{fmt(v)}</text>
          </g>
        ))}
        <path d={band("p95", "p05")} fill="rgba(57,135,229,0.10)" />
        <path d={band("p75", "p25")} fill="rgba(57,135,229,0.22)" />
        <path d={histPath} fill="none" stroke="var(--ink-2)" strokeWidth="1.8" />
        <path d={median} fill="none" stroke="#3987e5" strokeWidth="2" strokeDasharray="5 3" />
        <line x1={x(splitI)} x2={x(splitI)} y1={PAD.t} y2={H - PAD.b} stroke="var(--baseline)" strokeDasharray="2 3" />
        <text x={x(splitI)} y={H - 8} fill="var(--muted)" fontSize="10" textAnchor="middle">today</text>
        {[["p95", "top 5%"], ["p50", "median"], ["p05", "worst 5%"]].map(([k, lbl]) => (
          <text key={k} x={W - PAD.r + 6} y={y(fan.at(-1)[k]) + 3} fill="var(--ink-2)" fontSize="10">
            {lbl}
          </text>
        ))}
        {hv && <line x1={hv.x} x2={hv.x} y1={PAD.t} y2={H - PAD.b} stroke="var(--baseline)" strokeWidth="1" />}
      </svg>
      {hv && (
        <div className="fan-tip" style={{ left: Math.min(hv.x + 10, W - 150), top: 10 }}>
          <div className="dim" style={{ marginBottom: 3 }}>{hv.time}</div>
          {hv.rows.map(([k, v]) => (
            <div key={k}><span className="dim">{k}</span> <span className="mono">{fmt(v)}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}

/* When the simulated low arrives: % of futures per session (single hue). */
export function DayHistogram({ hist, height = 90 }) {
  if (!hist?.length) return null;
  const total = hist.reduce((a, b) => a + b, 0) || 1;
  const max = Math.max(...hist) / total || 1;
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height }}>
      {hist.map((c, i) => {
        const share = c / total;
        return (
          <div key={i} title={`Session ${i + 1}: low lands here in ${(share * 100).toFixed(0)}% of futures`}
            style={{
              flex: 1, minWidth: 3, borderRadius: "3px 3px 0 0",
              height: `${Math.max(3, (share / max) * 100)}%`,
              background: "rgba(57,135,229,0.55)",
            }} />
        );
      })}
    </div>
  );
}

/* Correlation heatmap: diverging red (-1) -> neutral (0) -> blue (+1). */
function lerp(a, b, t) { return Math.round(a + (b - a) * t); }
function divergingColor(v) {
  const neg = [208, 59, 59], mid = [56, 56, 53], pos = [57, 135, 229];
  const [f, t2] = v < 0 ? [mid, neg] : [mid, pos];
  const t = Math.min(Math.abs(v), 1);
  return `rgb(${lerp(f[0], t2[0], t)},${lerp(f[1], t2[1], t)},${lerp(f[2], t2[2], t)})`;
}

export function Heatmap({ tickers, matrix }) {
  if (!tickers?.length) return null;
  const n = tickers.length;
  return (
    <div className="hm" style={{ gridTemplateColumns: `56px repeat(${n}, 1fr)` }}>
      <div className="hd" />
      {tickers.map((t) => <div key={`c${t}`} className="hd">{t}</div>)}
      {matrix.map((row, i) => (
        [<div key={`r${tickers[i]}`} className="hd">{tickers[i]}</div>,
        ...row.map((v, j) => (
          <div key={`${i}-${j}`} className="cell" style={{ background: divergingColor(v) }} title={`${tickers[i]} × ${tickers[j]}: ${v.toFixed(2)}`}>
            {n <= 14 ? v.toFixed(2) : ""}
          </div>
        ))]
      ))}
    </div>
  );
}
