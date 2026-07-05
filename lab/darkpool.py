"""
Dark pool radar via FINRA's FREE official daily short-sale volume files.
SVR = ShortVolume/TotalVolume per ticker. DIX-style reading (counter-intuitive):
high SVR ~= market makers shorting to fill buy orders = buying pressure.
The signal is the z-score jump vs the ticker's own 10-day baseline, not the level.
Free, daily (published in the evening, T+0/T+1). Volumes only — no prices/direction.
"""
import datetime
import json
import statistics
import urllib.request


def _fetch_day(d, watch):
    url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research"})
        raw = urllib.request.urlopen(req, timeout=25).read().decode()
    except Exception:
        return None
    out = {}
    for line in raw.splitlines()[1:]:
        p = line.split("|")
        if len(p) >= 5 and p[1] in watch:
            try:
                sv, tv = float(p[2]), float(p[4])
                if tv > 0:
                    out[p[1]] = sv / tv
            except Exception:
                continue
    return out


def dark_svr(watchlist):
    watch = set(watchlist)
    days = []
    d = datetime.date.today()
    tries = 0
    while len(days) < 11 and tries < 25:
        d -= datetime.timedelta(days=1); tries += 1
        if d.weekday() >= 5:
            continue
        r = _fetch_day(d.strftime("%Y%m%d"), watch)
        if r:
            days.append((d.isoformat(), r))
    if not days:
        return None
    latest_date, latest = days[0]
    hist = days[1:]
    rows = []
    for t in sorted(latest):
        base = [h[1][t] for h in hist if t in h[1]]
        if len(base) < 5:
            continue
        mu, sd = statistics.mean(base), statistics.pstdev(base)
        z = (latest[t] - mu) / sd if sd > 0 else 0
        rows.append({"t": t, "svr": round(latest[t] * 100, 1), "avg10": round(mu * 100, 1), "z": round(z, 1)})
    rows.sort(key=lambda r: -abs(r["z"]))
    return {"as_of": latest_date, "rows": rows}
