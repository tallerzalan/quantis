import { useEffect, useRef, useState } from "react";
import { motion, useSpring, useTransform, useReducedMotion } from "framer-motion";

/* Verdict chip + optional explanation sentence: the interpretability layer. */
export function Verdict({ v, explain = false }) {
  if (!v) return null;
  return (
    <span className={`verdict v-${v.level}`} title={explain ? undefined : v.detail}>
      <span className="dot" />
      {v.label}
    </span>
  );
}

export function Explain({ v }) {
  if (!v) return null;
  return <div className={`explain ${v.level}`}>{v.detail}</div>;
}

export function InfoTip({ text, children }) {
  return (
    <span className="tooltip">
      {children ?? <span className="qmark">?</span>}
      <span className="tip">{text}</span>
    </span>
  );
}

/* Animated number: springs to new values. */
export function Ticker({ value, format, className }) {
  const reduced = useReducedMotion();
  const spring = useSpring(value ?? 0, { stiffness: 80, damping: 20 });
  const display = useTransform(spring, (v) => (format ? format(v) : v.toFixed(2)));
  useEffect(() => {
    if (reduced) spring.jump(value ?? 0);
    else spring.set(value ?? 0);
  }, [value, spring, reduced]);
  if (value == null) return <span className={className}>—</span>;
  return <motion.span className={className}>{display}</motion.span>;
}

/* Signature radial gauge for the Quantis Score (0-100). */
export function ScoreRing({ score, size = 72 }) {
  const r = size / 2 - 6;
  const level = score >= 80 ? "var(--up)" : score >= 50 ? "var(--ok)" : "var(--muted)";
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Quantis Score ${Math.round(score)}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--baseline)" strokeWidth="5" />
      <motion.circle
        cx={size / 2} cy={size / 2} r={r} fill="none"
        stroke={level} strokeWidth="5" strokeLinecap="round"
        style={{ rotate: -90, transformOrigin: "50% 50%" }}
        strokeDasharray={2 * Math.PI * r}
        initial={{ strokeDashoffset: 2 * Math.PI * r }}
        animate={{ strokeDashoffset: 2 * Math.PI * r * (1 - (score ?? 0) / 100) }}
        transition={{ type: "spring", stiffness: 60, damping: 16 }}
      />
      <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle"
        fill="var(--ink)" fontFamily="var(--display)" fontWeight="600" fontSize={size * 0.3}>
        {Math.round(score ?? 0)}
      </text>
    </svg>
  );
}

export function Tile({ label, value, sub, tip, valueClass = "" }) {
  return (
    <div className="tile">
      <div className="lbl">
        {label} {tip && <InfoTip text={tip} />}
      </div>
      <div className={`val ${valueClass}`}>{value}</div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="err">
      {String(error.message || error)}{" "}
      {onRetry && <button className="btn ghost sm" onClick={onRetry} style={{ marginLeft: 8 }}>Try again</button>}
    </div>
  );
}

export function Loading({ height = 120, label }) {
  return (
    <div className="skeleton" style={{ height, display: "grid", placeItems: "center" }}>
      {label && <span className="note" style={{ display: "flex", gap: 8, alignItems: "center" }}><span className="spin" /> {label}</span>}
    </div>
  );
}

/* Fetch hook with refresh + dependency on the global watchlist version. */
export function useFetch(fn, deps) {
  const [state, set] = useState({ data: null, error: null, loading: true });
  const seq = useRef(0);
  const run = () => {
    const id = ++seq.current;
    set((s) => ({ ...s, loading: true, error: null }));
    fn()
      .then((data) => id === seq.current && set({ data, error: null, loading: false }))
      .catch((error) => id === seq.current && set({ data: null, error, loading: false }));
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(run, deps);
  return { ...state, reload: run };
}

/* Sortable table. columns: [{key, label, render?, className?, tip?}] */
export function DataTable({ columns, rows, initialSort, onRowClick, max = 500 }) {
  const [sort, setSort] = useState(initialSort || { key: columns[1]?.key, dir: -1 });
  const sorted = [...(rows || [])].sort((a, b) => {
    const va = a[sort.key], vb = b[sort.key];
    if (va == null) return 1;
    if (vb == null) return -1;
    return (va > vb ? 1 : va < vb ? -1 : 0) * sort.dir;
  });
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="tbl">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? -s.dir : -1 }))}>
                {c.label}
                {c.tip && <> <InfoTip text={c.tip} /></>}
                {sort.key === c.key ? (sort.dir > 0 ? " ↑" : " ↓") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.slice(0, max).map((r, i) => (
            <tr key={r.ticker ?? i} className={onRowClick ? "clickable" : ""} onClick={onRowClick ? () => onRowClick(r) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={c.className ? c.className(r) : ""}>
                  {c.render ? c.render(r) : r[c.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export const pageMotion = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.22, ease: "easeOut" },
};

export const stagger = {
  animate: { transition: { staggerChildren: 0.06 } },
};

export const rise = {
  initial: { opacity: 0, y: 14 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3, ease: "easeOut" } },
};
