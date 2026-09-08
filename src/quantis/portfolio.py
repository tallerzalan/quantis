"""Paper-portfolio persistence and P&L tracking (portfolio.json in project root)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "portfolio.json"


def load(path: Path = DEFAULT_PATH) -> dict:
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"cash": 100.0, "positions": []}


def save(state: dict, path: Path = DEFAULT_PATH) -> None:
    Path(path).write_text(json.dumps(state, indent=2))


def add_position(state: dict, ticker: str, shares: float, cost: float) -> dict:
    """Add (or average into) a position. `cost` is per-share cost basis."""
    ticker = ticker.upper().strip()
    spend = shares * cost
    for p in state["positions"]:
        if p["ticker"] == ticker:
            total_shares = p["shares"] + shares
            p["cost"] = (p["shares"] * p["cost"] + spend) / total_shares
            p["shares"] = total_shares
            break
    else:
        state["positions"].append({"ticker": ticker, "shares": shares, "cost": cost})
    state["cash"] = round(state["cash"] - spend, 2)
    return state


def remove_position(state: dict, ticker: str, price: float) -> dict:
    """Close a position at `price`, returning proceeds to cash."""
    ticker = ticker.upper().strip()
    keep = []
    for p in state["positions"]:
        if p["ticker"] == ticker:
            state["cash"] = round(state["cash"] + p["shares"] * price, 2)
        else:
            keep.append(p)
    state["positions"] = keep
    return state


def valuation(state: dict, last_prices: pd.Series) -> pd.DataFrame:
    """Mark positions to market. Returns a frame with value / P&L per position."""
    rows = []
    for p in state["positions"]:
        last = float(last_prices.get(p["ticker"], float("nan")))
        value = p["shares"] * last
        cost_basis = p["shares"] * p["cost"]
        rows.append(
            {
                "ticker": p["ticker"],
                "shares": p["shares"],
                "cost": p["cost"],
                "last": last,
                "value": value,
                "pnl": value - cost_basis,
                "pnl_pct": (last / p["cost"] - 1) * 100 if p["cost"] else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def weights(state: dict, last_prices: pd.Series) -> pd.Series:
    val = valuation(state, last_prices)
    if val.empty or val["value"].sum() <= 0:
        return pd.Series(dtype=float)
    return (val.set_index("ticker")["value"] / val["value"].sum()).dropna()
