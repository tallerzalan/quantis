import { useEffect, useRef, useState } from "react";
import {
  CommandDialog, CommandInput, CommandList, CommandEmpty,
  CommandGroup, CommandItem, CommandShortcut,
} from "@/components/ui/command";
import {
  Activity, Lightbulb, CandlestickChart, LineChart, FlaskConical,
  Scale, ShieldAlert, Briefcase, Layers, Search, Plus,
} from "lucide-react";
import { get } from "../api";

const NAV = [
  { key: "today", label: "Today", hint: "Market overview", icon: Activity },
  { key: "ideas", label: "Ideas", hint: "Ranked trade setups", icon: Lightbulb },
  { key: "chart", label: "Charts", hint: "Candlesticks & signals", icon: CandlestickChart },
  { key: "forecast", label: "Forecast", hint: "Monte Carlo lab", icon: LineChart },
  { key: "factors", label: "Factors", hint: "Exposure & sectors", icon: Layers },
  { key: "backtest", label: "Backtest", hint: "Strategy lab", icon: FlaskConical },
  { key: "optimize", label: "Optimize", hint: "Portfolio construction", icon: Scale },
  { key: "risk", label: "Risk", hint: "Beta, VaR, drawdown", icon: ShieldAlert },
  { key: "portfolio", label: "Portfolio", hint: "Paper trades & P&L", icon: Briefcase },
];

/* ⌘K command palette: jump to any section or search any ticker on Yahoo. */
export default function CommandMenu({ open, setOpen, onNavigate, onPickTicker, onAddTicker }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const timer = useRef(null);

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [setOpen]);

  useEffect(() => {
    clearTimeout(timer.current);
    const text = q.trim();
    if (!text) { setResults([]); return; }
    timer.current = setTimeout(async () => {
      try {
        const r = await get(`/search?q=${encodeURIComponent(text)}`);
        setResults(r.results || []);
      } catch { setResults([]); }
    }, 240);
    return () => clearTimeout(timer.current);
  }, [q]);

  const nav = (key) => { onNavigate(key); setOpen(false); setQ(""); };
  const openTicker = (sym) => { onPickTicker(sym); setOpen(false); setQ(""); setResults([]); };
  const add = (sym, e) => { e.stopPropagation(); onAddTicker(sym); };

  return (
    <CommandDialog open={open} onOpenChange={setOpen} shouldFilter={!q.trim()}
      title="Command palette" description="Jump to a section or search any ticker">
      <CommandInput placeholder="Search a ticker, or jump to a section…" value={q} onValueChange={setQ} />
      <CommandList>
        <CommandEmpty>No matches.</CommandEmpty>
        {results.length > 0 && (
          <CommandGroup heading="Tickers">
            {results.map((r) => (
              <CommandItem key={r.symbol} value={`tk-${r.symbol}`} onSelect={() => openTicker(r.symbol)}>
                <Search className="opacity-60" />
                <span className="font-mono font-semibold text-[var(--ink)] min-w-[54px]">{r.symbol}</span>
                <span className="truncate text-[var(--muted)]">{r.name}</span>
                <button
                  onClick={(e) => add(r.symbol, e)}
                  className="ml-auto inline-flex items-center gap-1 text-[var(--accent)] hover:brightness-125"
                  title="Add to watchlist">
                  <Plus size={13} /> add
                </button>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandGroup heading="Go to">
          {NAV.map((n) => (
            <CommandItem key={n.key} value={`${n.label} ${n.hint}`} onSelect={() => nav(n.key)}>
              <n.icon className="opacity-70" />
              <span className="text-[var(--ink)]">{n.label}</span>
              <span className="text-[var(--muted)]">{n.hint}</span>
              <CommandShortcut>↵</CommandShortcut>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
