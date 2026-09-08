import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { get, post } from "../api";

/* Global ticker search: type anything on Yahoo Finance, click to add. */
export function SearchBox({ onPick, placeholder = "Add any stock… (e.g. NVDA)" }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const box = useRef(null);
  const timer = useRef(null);

  useEffect(() => {
    const close = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const search = (text) => {
    setQ(text);
    clearTimeout(timer.current);
    if (!text.trim()) { setResults([]); setOpen(false); return; }
    timer.current = setTimeout(async () => {
      try {
        const r = await get(`/search?q=${encodeURIComponent(text.trim())}`);
        setResults(r.results);
        setOpen(true);
      } catch { setResults([]); }
    }, 280);
  };

  const pick = async (sym) => {
    setBusy(true);
    try {
      await onPick(sym);
      setQ(""); setResults([]); setOpen(false);
    } finally { setBusy(false); }
  };

  return (
    <div className="search" ref={box}>
      <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
      </svg>
      <input
        value={q}
        placeholder={placeholder}
        onChange={(e) => search(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && q.trim()) pick(q.trim().toUpperCase()); }}
        aria-label="Search stocks"
      />
      {busy && <span className="spin" style={{ position: "absolute", right: 10, top: 9 }} />}
      <AnimatePresence>
        {open && results.length > 0 && (
          <motion.div className="search-pop"
            initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.15 }}>
            {results.map((r) => (
              <button key={r.symbol} onClick={() => pick(r.symbol)}>
                <span className="sym">{r.symbol}</span>
                <span className="nm">{r.name}</span>
                <span className="dim" style={{ fontSize: 10.5 }}>{r.exchange}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function BrandMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="13" width="3.4" height="8" rx="1" fill="var(--muted)" />
      <rect x="8.3" y="8" width="3.4" height="13" rx="1" fill="var(--ink-2)" />
      <rect x="13.6" y="4" width="3.4" height="17" rx="1" fill="var(--accent)" />
      <circle cx="19.4" cy="5.2" r="2.1" fill="none" stroke="var(--accent)" strokeWidth="1.5" />
    </svg>
  );
}

export default function TopBar({ watchlist, onAdd, onRemove, asOf, onOpenCmd }) {
  return (
    <header className="topbar">
      <div className="brand"><BrandMark />QUANT<b>IS</b></div>
      <button className="cmdk-trigger" onClick={onOpenCmd} aria-label="Open command palette">
        <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" />
        </svg>
        <span>Search ticker or jump to…</span>
        <kbd>⌘K</kbd>
      </button>
      <div className="wl-strip">
        <div className="wl-chips">
          <AnimatePresence initial={false}>
            {watchlist.map((t) => (
              <motion.span key={t.symbol} className="chip" layout
                initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.8 }}
                transition={{ duration: 0.15 }}>
                {t.symbol}
                <button className="x" onClick={() => onRemove(t.symbol)} aria-label={`Remove ${t.symbol}`}>×</button>
              </motion.span>
            ))}
          </AnimatePresence>
        </div>
      </div>
      <span className="asof">{asOf ? `data as of ${asOf}` : ""}</span>
    </header>
  );
}
