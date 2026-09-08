import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { get, post } from "./api";
import { useFetch } from "./components/ui";
import TopBar from "./components/TopBar";
import CommandMenu from "./components/CommandMenu";
import Today from "./pages/Today";
import Ideas from "./pages/Ideas";
import ChartPage from "./pages/ChartPage";
import Forecast from "./pages/Forecast";
import Factors from "./pages/Factors";
import Backtest from "./pages/Backtest";
import Optimize from "./pages/Optimize";
import Risk from "./pages/Risk";
import Portfolio from "./pages/Portfolio";

const icon = (d) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    {d}
  </svg>
);

const NAV = [
  { key: "today", label: "Today", icon: icon(<><path d="M3 12h4l3-8 4 16 3-8h4" /></>) },
  { key: "ideas", label: "Ideas", icon: icon(<><path d="M12 2v3M4.9 4.9l2.1 2.1M2 12h3M19 12h3M17 7l2.1-2.1" /><path d="M9 18h6M10 21h4M12 8a4 4 0 0 1 4 4c0 1.5-.8 2.4-1.6 3.2-.5.5-.9 1-1 1.8h-2.8c-.1-.8-.5-1.3-1-1.8C8.8 14.4 8 13.5 8 12a4 4 0 0 1 4-4Z" /></>) },
  { key: "chart", label: "Charts", icon: icon(<><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M8 14v3M12 9v8M16 12v5" /></>) },
  { key: "forecast", label: "Forecast", icon: icon(<><path d="M3 17c4-1 6-8 9-8" /><path d="M12 9c2 0 4 2.5 5.5 5M12 9c2.5-.5 6-3 8-5.5" /><path d="M12 9c1.5 1.5 2 6.5 2.5 11" /></>) },
  { key: "factors", label: "Factors", icon: icon(<><path d="m12 2 9 5-9 5-9-5 9-5Z" /><path d="m3 12 9 5 9-5M3 17l9 5 9-5" /></>) },
  { key: "backtest", label: "Backtest", icon: icon(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></>) },
  { key: "optimize", label: "Optimize", icon: icon(<><circle cx="7" cy="17" r="2.5" /><circle cx="17" cy="7" r="2.5" /><path d="M9 15.2 15 8.8M4 21c0-7 4.5-12.5 13-16" /></>) },
  { key: "risk", label: "Risk", icon: icon(<><path d="M12 3 4 6.5v5c0 4.6 3.4 8.4 8 9.5 4.6-1.1 8-4.9 8-9.5v-5L12 3Z" /><path d="M12 8v4M12 15.5v.5" /></>) },
  { key: "portfolio", label: "Portfolio", icon: icon(<><rect x="3" y="7" width="18" height="13" rx="2" /><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18" /></>) },
];

export default function App() {
  const [page, setPage] = useState("today");
  const [chartTicker, setChartTicker] = useState("SPY");
  const [capital, setCapital] = useState(100);
  const [wlVersion, setWlVersion] = useState(0);
  const [toast, setToast] = useState(null);
  const [cmdOpen, setCmdOpen] = useState(false);
  const wl = useFetch(() => get("/watchlist"), [wlVersion]);
  const market = useFetch(() => get("/market"), [wlVersion]);
  const watchlist = wl.data?.tickers ?? [];

  const notify = (msg, isError = false) => {
    setToast({ msg, isError, id: Date.now() });
    setTimeout(() => setToast((t) => (t?.msg === msg ? null : t)), 4200);
  };

  const addTicker = async (sym) => {
    try {
      await post("/watchlist/add", { ticker: sym });
      setWlVersion((v) => v + 1);
      notify(`${sym.toUpperCase()} added to your watchlist.`);
    } catch (e) {
      notify(String(e.message || e), true);
    }
  };

  const removeTicker = async (sym) => {
    try {
      await post("/watchlist/remove", { ticker: sym });
      setWlVersion((v) => v + 1);
    } catch (e) {
      notify(String(e.message || e), true);
    }
  };

  const goChart = (t) => { setChartTicker(t); setPage("chart"); };

  const pages = {
    today: <Today wlVersion={wlVersion} goChart={goChart} />,
    ideas: <Ideas wlVersion={wlVersion} capital={capital} goChart={goChart} notify={notify} />,
    chart: <ChartPage wlVersion={wlVersion} ticker={chartTicker} setTicker={setChartTicker} watchlist={watchlist} onAddToWatchlist={addTicker} />,
    forecast: <Forecast ticker={chartTicker} setTicker={setChartTicker} watchlist={watchlist} />,
    factors: <Factors wlVersion={wlVersion} capital={capital} goChart={goChart} />,
    backtest: <Backtest wlVersion={wlVersion} capital={capital} />,
    optimize: <Optimize wlVersion={wlVersion} capital={capital} watchlist={watchlist} />,
    risk: <Risk wlVersion={wlVersion} goChart={goChart} watchlist={watchlist} />,
    portfolio: <Portfolio wlVersion={wlVersion} watchlist={watchlist} notify={notify} />,
  };

  return (
    <>
    <div className="aurora" aria-hidden="true" />
    <div className="grain" aria-hidden="true" />
    <div className="shell">
      <TopBar watchlist={watchlist} onAdd={addTicker} onRemove={removeTicker} asOf={market.data?.as_of} onOpenCmd={() => setCmdOpen(true)} />
      <CommandMenu open={cmdOpen} setOpen={setCmdOpen} onNavigate={setPage} onPickTicker={goChart} onAddTicker={addTicker} />
      <nav className="nav" aria-label="Sections">
        {NAV.map((n) => (
          <button key={n.key} className={page === n.key ? "on" : ""} onClick={() => setPage(n.key)}>
            {n.icon}
            {n.label}
          </button>
        ))}
        <div style={{ marginTop: "auto", padding: "0 2px" }}>
          <label className="field" style={{ fontSize: 10 }}>
            Capital $
            <input type="number" min="10" step="10" value={capital}
              onChange={(e) => setCapital(Math.max(10, Number(e.target.value) || 100))}
              style={{ padding: "4px 6px", fontSize: 12 }} />
          </label>
        </div>
      </nav>
      <main className="main">
        <AnimatePresence mode="wait">
          <motion.div key={page}
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2, ease: "easeOut" }}>
            {pages[page]}
          </motion.div>
        </AnimatePresence>
      </main>
      <AnimatePresence>
        {toast && (
          <motion.div key={toast.id}
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 10 }}
            style={{
              position: "fixed", bottom: 22, right: 22, zIndex: 100,
              background: toast.isError ? "rgba(208,59,59,0.95)" : "var(--surface-3)",
              border: "1px solid var(--baseline)", color: "#fff",
              padding: "10px 16px", borderRadius: 10, fontSize: 13, maxWidth: 380,
              boxShadow: "0 12px 32px rgba(0,0,0,0.5)",
            }}>
            {toast.msg}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </>
  );
}
