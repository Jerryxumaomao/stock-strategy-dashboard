"""Earnings radar: upcoming earnings for the watchlist (next N days) via free yfinance.
Rendered with the rule-10/11 windows: buy straddle T-3..T-1 and close BEFORE the
announcement (historically +3.3%); holding through = -5~-14% avg with IV crush ~-38%."""
import datetime


def get_earnings(watchlist, days=21):
    import yfinance as yf
    today = datetime.date.today()
    horizon = today + datetime.timedelta(days=days)
    out = []
    for t in watchlist:
        try:
            ed = yf.Ticker(t).earnings_dates
            if ed is None or ed.empty:
                continue
            for ts in ed.index:
                d = ts.date()
                if today <= d <= horizon:
                    out.append({"t": t, "date": d.isoformat(), "days": (d - today).days})
                    break
        except Exception:
            continue
    out.sort(key=lambda x: x["date"])
    return out
