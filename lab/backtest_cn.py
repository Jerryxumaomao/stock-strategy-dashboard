"""
A-share backtest engine — same strategies as backtest.py, but models the two A-share
realities that make US backtests LIE about A-share tradability:

  1. 涨停封死买不进 (sealed limit-up): a breakout day that gaps to a locked limit-up
     (一字板/T字板) CANNOT be bought. US engines happily "fill" it — the single biggest
     reason US breakout expectancy overstates A-share reality. We SKIP such entries.
  2. 跌停封死卖不出 (sealed limit-down): when your stop triggers but the day is locked
     limit-down, you are trapped — no liquidity. You exit only on the first later day
     that isn't locked-down, usually at a WORSE price (gapped through the stop). This
     makes stops in A-shares more expensive than US backtests assume.

Also respects T+1 implicitly: exits start at i+1 (you cannot sell the entry day).
Limit fraction defaults to 0.10 (主板); pass 0.20 (创业/科创), 0.30 (北交所), 0.05 (ST).

Everything else (entry conditions, R accounting, metrics) mirrors backtest.py so the two
engines are directly comparable — the DELTA is exactly the A-share friction.
"""
from .indicators import sma, atr
from .backtest import _uptrend, _rec, agg  # reuse identical uptrend/record/aggregate


def _rec_capped(*a):
    """A股妖股单笔可涨数十倍,ATR止损下 R 会算出 100+,一笔离群就毁掉期望值统计。
    缩尾到 [-10, 20]R:单笔最多亏10R(封跌停困住可穿透止损)、赢20R封顶。"""
    r = _rec(*a)
    r["R"] = max(-10.0, min(20.0, r["R"]))
    return r


def limit_flags(bars, lim=0.10):
    """Per-bar sealed-limit flags. up[i]=couldn't buy (sealed 涨停), dn[i]=couldn't sell (sealed 跌停).
    'Sealed' = the whole day traded at the limit (intraday low at limit-up, or high at limit-down)."""
    C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    n = len(bars); up = [False] * n; dn = [False] * n
    for i in range(1, n):
        pc = C[i - 1]
        if pc <= 0:
            continue
        eps = pc * 0.004  # tolerance for rounding to the exact limit price
        if L[i] >= pc * (1 + lim) - eps:   # low sat at limit-up all day -> sealed up
            up[i] = True
        if H[i] <= pc * (1 - lim) + eps:   # high sat at limit-down all day -> sealed down
            dn[i] = True
    return up, dn


def _trail_exit_cn(C, H, L, n, i, stop, dn):
    """Exit starting T+1. If an exit triggers on a sealed-limit-down day, you're trapped:
    exit only on the first later non-locked day, at that day's close (models gapping through)."""
    j = i + 1
    while j < n and j <= i + 80:
        if L[j] <= stop:
            if dn[j]:  # stop hit but 跌停封死 — can't sell, carry to first sellable day
                k = j
                while k < n and dn[k]:
                    k += 1
                xi = min(k, n - 1)
                return C[xi], xi, "stop_trapped"
            return stop, j, "stop"
        s = sma(C, 50, j)
        if s and C[j] < s:
            if dn[j]:
                k = j
                while k < n and dn[k]:
                    k += 1
                xi = min(k, n - 1)
                return C[xi], xi, "trail_trapped"
            return C[j], j, "trail"
        j += 1
    xi = min(j, n - 1)
    return C[xi], xi, "timeout"


def dip_trades(bars, reentry=False, lim=0.10):
    n = len(bars); C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    up, dn = limit_flags(bars, lim)
    tr = []; i = 200; last = -999
    while i < n - 1:
        u = _uptrend(C, i)
        near_high = C[i] >= max(H[max(0, i - 251):i + 1]) * 0.75
        if u and u[0] and near_high and L[i] <= u[1] * 1.03 and C[i] > u[1] * 0.97 and C[i] > C[i - 1] and (i - last) >= 10:
            if up[i]:            # 涨停封死当天买不进 -> 放弃该入场(A股现实)
                i += 1; continue
            entry = C[i]; stop = min(L[i - 4:i + 1]) * 0.99
            if stop >= entry:
                i += 1; continue
            risk = entry - stop; ex, xi, why = _trail_exit_cn(C, H, L, n, i, stop, dn)
            seg_low = min(L[i + 1:xi + 1]) if xi > i else entry
            fw = H[xi + 1:min(xi + 21, n)]
            tr.append(_rec_capped(entry, ex, risk, seg_low, fw, why))
            last = xi; i = xi + 1
        else:
            i += 1
    return tr


def brk_trades(bars, lim=0.10):
    n = len(bars); C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    up, dn = limit_flags(bars, lim)
    tr = []; i = 200; last = -999
    while i < n - 1:
        u = _uptrend(C, i)
        if u and u[0] and i >= 40 and C[i] >= max(H[i - 40:i]) and C[i] > C[i - 1] and (i - last) >= 10:
            if up[i]:            # 突破日封死涨停 -> 买不进(A股突破策略被高估的核心原因)
                i += 1; continue
            entry = C[i]; stop = min(L[i - 10:i + 1]) * 0.98
            if stop >= entry:
                i += 1; continue
            risk = entry - stop; ex, xi, why = _trail_exit_cn(C, H, L, n, i, stop, dn)
            fw = H[xi + 1:min(xi + 21, n)]
            tr.append(_rec_capped(entry, ex, risk, min(L[i + 1:xi + 1]) if xi > i else entry, fw, why))
            last = xi; i = xi + 1
        else:
            i += 1
    return tr


def brk_atr_trades(bars, k=2.0, lim=0.10):
    n = len(bars); C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    up, dn = limit_flags(bars, lim)
    tr = []; i = 200; last = -999
    while i < n - 1:
        u = _uptrend(C, i)
        if u and u[0] and i >= 40 and C[i] >= max(H[i - 40:i]) and C[i] > C[i - 1] and (i - last) >= 10:
            if up[i]:
                i += 1; continue
            entry = C[i]; a = atr(H, L, C, i); stop = entry - k * a
            if a <= 0 or stop >= entry:
                i += 1; continue
            risk = entry - stop; ex, xi, why = _trail_exit_cn(C, H, L, n, i, stop, dn)
            fw = H[xi + 1:min(xi + 21, n)]
            tr.append(_rec_capped(entry, ex, risk, min(L[i + 1:xi + 1]) if xi > i else entry, fw, why))
            last = xi; i = xi + 1
        else:
            i += 1
    return tr


def friction_report(bars, lim=0.10):
    """How much A-share friction is in THIS name's history: sealed limit-up/down day counts,
    and skipped-breakout-entry count vs the US engine. Surfaces WHY the two engines differ."""
    from . import backtest as US
    up, dn = limit_flags(bars, lim)
    us_brk = len(US.brk_trades(bars)); cn_brk = len(brk_trades(bars, lim))
    trapped = sum(1 for t in brk_trades(bars, lim) + dip_trades(bars, lim=lim) if "trapped" in t["reason"])
    return {"sealed_up_days": sum(up), "sealed_dn_days": sum(dn),
            "brk_entries_us": us_brk, "brk_entries_cn": cn_brk,
            "brk_skipped_sealed_up": us_brk - cn_brk, "limit_trapped_exits": trapped,
            "limit_pct": round(lim * 100)}
