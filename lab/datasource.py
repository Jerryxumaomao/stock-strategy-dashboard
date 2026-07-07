"""
Pluggable market-data sources. Default = Yahoo Finance (yfinance, free, no account).

Every source returns a list of daily bars, oldest first:
    [{"date": "YYYY-MM-DD", "o": open, "h": high, "l": low, "c": close}, ...]
A-share bars additionally carry "v" (volume) and "turnover" (换手率 %), which the
A-share factor logic (reversal, liquidity, sentiment) relies on; US strategies ignore them.

To add a broker/platform (IBKR, TradingView, Alpaca, ...), implement a function with
the same signature and register it in SOURCES.

=== A-share branch note ===
Chinese A-shares differ structurally from US (price limits, T+1, long-only, call auction).
Read docs/A股量化知识手册.md BEFORE applying any strategy — momentum/breakout logic that
works in the US is WEAKER or inverted in A-shares (short-term reversal dominates). The
akshare source below is free and needs no token; tickers are 6-digit codes (600519, 000001,
300750, 688981, 8-prefix for BSE).
"""
import datetime


def _period_to_start(period):
    """'5y'/'1y'/'6mo'/'250d' -> YYYYMMDD start date (akshare wants explicit dates)."""
    n = int("".join(c for c in period if c.isdigit()) or 5)
    unit = "".join(c for c in period if c.isalpha()).lower() or "y"
    days = {"y": 365, "mo": 30, "m": 30, "d": 1, "w": 7}.get(unit, 365) * n
    return (datetime.date.today() - datetime.timedelta(days=days)).strftime("%Y%m%d")


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


def _ashare_prefix(code):
    """Exchange prefix from a 6-digit A-share code (sina wants sh/sz/bj)."""
    if code[0] in "6" or code[:3] in ("900",):
        return "sh"
    if code[0] in "045" or code[0] == "8" or code[:3] in ("430", "830", "920"):
        return "bj" if (code[0] in "48" or code[:3] in ("430", "830", "920")) else "sz"
    return "sz"


def akshare_history(ticker, period="5y"):
    """A-share daily bars via akshare (free, no token). 前复权 (qfq) adjusted.
    ticker = 6-digit code ('600519', '000001', '300750', '688981', '830799').
    Dual channel: 东财 (stock_zh_a_hist) first, 新浪 (stock_zh_a_daily) fallback — one is
    reachable from mainland, the other often works behind a VPN, so a friend anywhere gets data.
    Returns standard bars + 'v' (volume) + 'turnover' (换手率 %)."""
    import akshare as ak
    code = "".join(c for c in str(ticker) if c.isdigit()).zfill(6)
    start, end = _period_to_start(period), datetime.date.today().strftime("%Y%m%d")

    # channel 1: 东财 (richer: 换手率/涨跌幅 native; best from mainland)
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is not None and not df.empty:
            bars = []
            for _, r in df.iterrows():
                try:
                    bars.append({"date": str(r["日期"])[:10], "o": float(r["开盘"]), "h": float(r["最高"]),
                                 "l": float(r["最低"]), "c": float(r["收盘"]), "v": float(r["成交量"]),
                                 "turnover": float(r.get("换手率", 0) or 0)})
                except Exception:
                    continue
            if bars:
                return [b for b in bars if b["c"] == b["c"]]
    except Exception:
        pass

    # channel 2: 新浪 (turnover is a fraction -> x100 for %); reachable when 东财 is blocked
    try:
        df = ak.stock_zh_a_daily(symbol=_ashare_prefix(code) + code, adjust="qfq")
        cutoff = datetime.datetime.strptime(start, "%Y%m%d").date()
        bars = []
        for _, r in df.iterrows():
            try:
                d = r["date"]
                d = d if isinstance(d, str) else d.strftime("%Y-%m-%d")
                if datetime.datetime.strptime(d[:10], "%Y-%m-%d").date() < cutoff:
                    continue
                bars.append({"date": d[:10], "o": float(r["open"]), "h": float(r["high"]),
                             "l": float(r["low"]), "c": float(r["close"]), "v": float(r["volume"]),
                             "turnover": round(float(r.get("turnover", 0) or 0) * 100, 3)})
            except Exception:
                continue
        return [b for b in bars if b["c"] == b["c"]]
    except Exception:
        return []


def akshare_index(symbol="sh000300", period="5y"):
    """A-share INDEX daily bars (for the market-gate; 000300=沪深300, 000905=中证500,
    000852=中证1000, 000985=中证全指). Symbol takes an sh/sz prefix."""
    import akshare as ak
    try:
        df = ak.stock_zh_index_daily(symbol=symbol)
    except Exception:
        return []
    cutoff = datetime.datetime.strptime(_period_to_start(period), "%Y%m%d").date()
    bars = []
    for _, r in df.iterrows():
        try:
            d = r["date"]
            d = d if isinstance(d, str) else d.strftime("%Y-%m-%d")
            if datetime.datetime.strptime(d[:10], "%Y-%m-%d").date() < cutoff:
                continue
            bars.append({"date": d[:10], "o": float(r["open"]), "h": float(r["high"]),
                         "l": float(r["low"]), "c": float(r["close"])})
        except Exception:
            continue
    return bars


SOURCES = {
    "yahoo": yahoo_history,
    "ibkr": ibkr_history,
    "tradingview": tradingview_history,
    "akshare": akshare_history,   # A-share (China mainland); see docs/A股量化知识手册.md
}


def get_history(ticker, source="yahoo", period="5y"):
    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Available: {list(SOURCES)}")
    return SOURCES[source](ticker, period)
