"""
Pluggable market-data sources. Default = Yahoo Finance (yfinance, free, no account).

Every source returns a list of daily bars, oldest first:
    [{"date": "YYYY-MM-DD", "o": open, "h": high, "l": low, "c": close}, ...]

To add a broker/platform (IBKR, TradingView, Alpaca, ...), implement a function with
the same signature and register it in SOURCES.
"""


def yahoo_history(ticker, period="5y"):
    import yfinance as yf
    df = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=True)
    bars = []
    for idx, row in df.iterrows():
        try:
            bars.append({
                "date": idx.strftime("%Y-%m-%d"),
                "o": float(row["Open"]), "h": float(row["High"]),
                "l": float(row["Low"]), "c": float(row["Close"]),
            })
        except Exception:
            continue
    return [b for b in bars if b["c"] == b["c"]]  # drop NaN


def ibkr_history(ticker, period="5y"):
    # Placeholder: wire up ib_insync / IBKR client here if you have an account.
    raise NotImplementedError("IBKR source not configured. Use 'yahoo' (default) or implement this.")


def tradingview_history(ticker, period="5y"):
    # Placeholder: wire up tvdatafeed / a TradingView reader here.
    raise NotImplementedError("TradingView source not configured. Use 'yahoo' (default) or implement this.")


SOURCES = {
    "yahoo": yahoo_history,
    "ibkr": ibkr_history,
    "tradingview": tradingview_history,
}


def get_history(ticker, source="yahoo", period="5y"):
    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Available: {list(SOURCES)}")
    return SOURCES[source](ticker, period)
