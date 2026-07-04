"""
Market-wide movers radar (not limited to the watchlist). Zero-cost local scan via yfinance.
  * Stocks: Yahoo predefined screeners (day_gainers / day_losers / most_actives) + volume
    ratio vs 3-month average — volume >= 3x is the "real" unusual-activity highlight.
  * Options UOA: for the top gainers + most actives, pull the nearest 2 expiries and flag
    contracts with volume >= 1000 and volume/OI >= 3 (fresh positioning >> existing interest).
Honest limits: Yahoo quotes ~15-min delayed; UOA cannot tell buyer- vs seller-initiated flow
(needs tick data); huge near-expiry prints can be market-maker hedging. Directional hint only.
"""
import datetime


def stock_movers(count=15):
    import yfinance as yf
    out = {}
    for key in ["day_gainers", "day_losers", "most_actives"]:
        rows = []
        try:
            r = yf.screen(key, count=25) if hasattr(yf, "screen") else None
            quotes = (r or {}).get("quotes", [])
        except Exception as e:
            out[key] = {"error": str(e)[:120]}; continue
        for q in quotes[:count]:
            try:
                vol = q.get("regularMarketVolume") or 0
                avg = q.get("averageDailyVolume3Month") or 0
                rows.append({
                    "s": q.get("symbol"), "n": (q.get("shortName") or "")[:28],
                    "px": round(q.get("regularMarketPrice") or 0, 2),
                    "chg": round(q.get("regularMarketChangePercent") or 0, 1),
                    "volx": round(vol / avg, 1) if avg else None,
                    "mc": round((q.get("marketCap") or 0) / 1e9, 1),
                })
            except Exception:
                continue
        out[key] = rows
    return out


def uoa_scan(tickers, max_tickers=8, top=12):
    import yfinance as yf
    hits = []
    for t in tickers[:max_tickers]:
        try:
            tk = yf.Ticker(t)
            for e in (tk.options or [])[:2]:
                ch = tk.option_chain(e)
                for kind, df in (("C", ch.calls), ("P", ch.puts)):
                    for _, r in df.iterrows():
                        vol = int(r.get("volume") or 0); oi = int(r.get("openInterest") or 0)
                        if vol >= 1000 and oi > 0 and vol / oi >= 3:
                            hits.append({"t": t, "kind": kind, "expiry": e, "k": float(r["strike"]),
                                         "vol": vol, "oi": oi, "ratio": round(vol / oi, 1),
                                         "prem_m": round(vol * float(r.get("lastPrice") or 0) * 100 / 1e6, 2)})
        except Exception:
            continue
    hits.sort(key=lambda x: -x["prem_m"])
    return hits[:top]


def get_movers():
    mv = stock_movers()
    seeds = []
    for k in ["day_gainers", "most_actives"]:
        for r in (mv.get(k) or [])[:5]:
            if isinstance(r, dict) and r.get("s") and r["s"] not in seeds:
                seeds.append(r["s"])
    return {"as_of": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "movers": mv, "uoa": uoa_scan(seeds)}
