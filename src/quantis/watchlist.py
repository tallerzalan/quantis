"""User-editable watchlist persisted to watchlist.json (drives every section)."""
from __future__ import annotations

import json
from pathlib import Path

from . import universe as uni

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "watchlist.json"


def load(path: Path = DEFAULT_PATH) -> list[str]:
    if Path(path).exists():
        try:
            tickers = json.loads(Path(path).read_text())["tickers"]
            if isinstance(tickers, list) and tickers:
                return [t.upper() for t in tickers]
        except (json.JSONDecodeError, KeyError, OSError):
            pass
    return uni.all_tickers()


def save(tickers: list[str], path: Path = DEFAULT_PATH) -> None:
    Path(path).write_text(json.dumps({"tickers": tickers}, indent=2))


def add(ticker: str, path: Path = DEFAULT_PATH) -> list[str]:
    tickers = load(path)
    t = ticker.upper().strip()
    if t and t not in tickers:
        tickers.append(t)
        save(tickers, path)
    return tickers


def remove(ticker: str, path: Path = DEFAULT_PATH) -> list[str]:
    tickers = [t for t in load(path) if t != ticker.upper().strip()]
    save(tickers, path)
    return tickers


def reset(path: Path = DEFAULT_PATH) -> list[str]:
    tickers = uni.all_tickers()
    save(tickers, path)
    return tickers


def group_of(ticker: str) -> str:
    g = uni.group_of(ticker)
    return "My additions" if g == "Other" else g
