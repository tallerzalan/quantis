"""Curated universe of liquid, volatile tickers suited to a 1-7 day swing horizon."""

BENCHMARK = "SPY"

UNIVERSE: dict[str, list[str]] = {
    "Index ETFs": ["SPY", "QQQ", "IWM", "DIA"],
    "Leveraged ETFs": ["TQQQ", "SOXL", "SPXL", "TNA", "LABU", "UPRO"],
    "Mega Tech": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA", "AVGO", "NFLX"],
    "Semis": ["AMD", "MU", "MRVL", "ARM", "SMCI", "TSM", "INTC", "QCOM", "LRCX", "AMAT"],
    "High Beta / Fintech": [
        "PLTR", "COIN", "HOOD", "MSTR", "SOFI", "RBLX", "RIOT", "MARA",
        "PYPL", "AFRM", "UPST", "DKNG",
    ],
    "Growth / Momentum": [
        "SHOP", "NET", "CRWD", "SNOW", "DDOG", "PANW", "UBER", "ABNB",
        "DASH", "CVNA", "APP", "VRT",
    ],
    "EV / Energy": ["RIVN", "LCID", "NIO", "ENPH", "FSLR"],
    "Retail Favorites": ["GME", "AMC"],
}


def all_tickers() -> list[str]:
    """Flat, de-duplicated ticker list (benchmark included via Index ETFs)."""
    seen: dict[str, None] = {}
    for group in UNIVERSE.values():
        for t in group:
            seen.setdefault(t, None)
    return list(seen)


def group_of(ticker: str) -> str:
    for group, tickers in UNIVERSE.items():
        if ticker in tickers:
            return group
    return "Other"
