"""
Backtest engine (deterministic, pure Python). Two strategies + shared exit:
  dip  = trend pullback to SMA50 + reversal bar   (chanlun-2nd-buy / SEPA pullback proxy)
  brk  = breakout above the recent 30-40d high     (SEPA pivot / momentum)
  exit = initial swing-low stop, then trail on SMA50 (let winners run)
Metrics: win_rate, expectancy in R (risk = entry-stop), plus timing diagnostics
  (entry MAE, post-exit upside "left on table", false-stop rate).
This is a reproducible *proxy* of a discretionary method, not strict chanlun.
"""
from .indicators import sma, atr


def _trail_exit(C, H, L, n, i, stop):
    j = i + 1
    while j < n and j <= i + 80:
        if L[j] <= stop:
            return stop, j, "stop"
        s = sma(C, 50, j)
        if s and C[j] < s:
            return C[j], j, "trail"
        j += 1
    xi = min(j, n - 1)
    return C[xi], xi, "timeout"


def _uptrend(C, i):
    s50 = sma(C, 50, i); s150 = sma(C, 150, i); s200 = sma(C, 200, i)
    s2p = sma(C, 200, i - 20) if i - 20 >= 199 else None
    if None in (s50, s150, s200, s2p):
        return None
    return (C[i] > s200 and s50 > s150 and s200 > s2p, s50)


def dip_trades(bars, reentry=False):
    n = len(bars); C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    tr = []; i = 200; last = -999
    while i < n - 1:
        u = _uptrend(C, i)
        if u and u[0] and L[i] <= u[1] * 1.03 and C[i] > u[1] * 0.97 and C[i] > C[i - 1] and (i - last) >= 10:
            entry = C[i]; stop = min(L[i - 4:i + 1]) * 0.99
            if stop >= entry:
                i += 1; continue
            risk = entry - stop; ex, xi, why = _trail_exit(C, H, L, n, i, stop)
            seg_low = min(L[i + 1:xi + 1]) if xi > i else entry
            fw = H[xi + 1:min(xi + 21, n)]
            tr.append(_rec(entry, ex, risk, seg_low, fw, why))
            if reentry and why == "stop":
                k = xi + 1
                while k < n and k <= xi + 15:
                    s50k = sma(C, 50, k)
                    if s50k and C[k] < s50k:
                        break
                    if C[k] >= entry and s50k and C[k] > s50k:
                        rs = min(L[k - 4:k + 1]) * 0.99
                        if rs < C[k]:
                            rex, rxi, rw = _trail_exit(C, H, L, n, k, rs)
                            tr.append(_rec(C[k], rex, C[k] - rs, min(L[k + 1:rxi + 1]) if rxi > k else C[k], H[rxi + 1:min(rxi + 21, n)], rw))
                            xi = rxi
                        break
                    k += 1
            last = xi; i = xi + 1
        else:
            i += 1
    return tr


def brk_trades(bars):
    n = len(bars); C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    tr = []; i = 200; last = -999
    while i < n - 1:
        u = _uptrend(C, i)
        if u and u[0] and i >= 40 and C[i] >= max(H[i - 40:i]) and C[i] > C[i - 1] and (i - last) >= 10:
            entry = C[i]; stop = min(L[i - 10:i + 1]) * 0.98
            if stop >= entry:
                i += 1; continue
            risk = entry - stop; ex, xi, why = _trail_exit(C, H, L, n, i, stop)
            fw = H[xi + 1:min(xi + 21, n)]
            tr.append(_rec(entry, ex, risk, min(L[i + 1:xi + 1]) if xi > i else entry, fw, why))
            last = xi; i = xi + 1
        else:
            i += 1
    return tr


def brk_atr_trades(bars, k=2.0):
    """Breakout entry with an ATR-based wide stop — for high-volatility names that
    get whipsawed out by a tight swing-low stop."""
    n = len(bars); C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    tr = []; i = 200; last = -999
    while i < n - 1:
        u = _uptrend(C, i)
        if u and u[0] and i >= 40 and C[i] >= max(H[i - 40:i]) and C[i] > C[i - 1] and (i - last) >= 10:
            entry = C[i]; a = atr(H, L, C, i); stop = entry - k * a
            if a <= 0 or stop >= entry:
                i += 1; continue
            risk = entry - stop; ex, xi, why = _trail_exit(C, H, L, n, i, stop)
            fw = H[xi + 1:min(xi + 21, n)]
            tr.append(_rec(entry, ex, risk, min(L[i + 1:xi + 1]) if xi > i else entry, fw, why))
            last = xi; i = xi + 1
        else:
            i += 1
    return tr


def hold_stats(bars):
    """Buy-and-hold profile: total return, CAGR, and the worst drawdown you'd have to endure.
    Used to flag strong secular uptrends where active trading (with stops) underperforms
    simply holding the (unlevered) stock — the 'position/hold' strategy."""
    C = [b["c"] for b in bars]
    n = len(C)
    if n < 2 or C[0] <= 0:
        return {"buy_hold_pct": 0, "cagr": 0, "max_dd": 0}
    yrs = n / 252
    bh = (C[-1] / C[0] - 1) * 100
    cagr = ((C[-1] / C[0]) ** (1 / yrs) - 1) * 100 if yrs > 0 else 0
    peak = C[0]; dd = 0
    for x in C:
        peak = max(peak, x)
        dd = min(dd, (x - peak) / peak)
    return {"buy_hold_pct": round(bh, 0), "cagr": round(cagr, 1), "max_dd": round(dd * 100, 0)}


def _rec(entry, ex, risk, seg_low, fw, why):
    mae = (entry - seg_low) / entry * 100
    post_up = ((max(fw) - ex) / ex * 100) if fw else 0.0
    return {"R": (ex - entry) / risk if risk > 0 else 0.0, "win": ex > entry,
            "mae": mae, "post_up": post_up, "reason": why,
            "reclaim": (max(fw) >= entry) if fw else False}


def agg(trades):
    if not trades:
        return {"n": 0, "win_rate": 0, "expectancy_R": 0}
    import statistics
    wins = [t for t in trades if t["win"]]
    stops = [t for t in trades if t["reason"] == "stop"]
    out = {
        "n": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "expectancy_R": round(statistics.mean([t["R"] for t in trades]), 2),
        "avg_post_exit_upside": round(statistics.mean([t["post_up"] for t in trades]), 1),
        "false_stop_rate": round(sum(1 for t in stops if t["reclaim"]) / len(stops) * 100, 1) if stops else 0,
    }
    return out
