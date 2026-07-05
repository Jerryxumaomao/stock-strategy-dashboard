"""
Options analytics (research-driven). Methodology:
  * Volatility cone (Sinclair): rolling realized vol percentiles from daily bars.
  * Implied vs realized: ATM straddle price -> implied move; compare vs the empirical
    |move| distribution over the same horizon. imp/real > 1.5 = heavy vol tax for buyers.
  * Contract scoring: empirical EV from historical T-day return windows (no GBM assumption).
  * 4 expiry buckets: lottery 7-21d (STRICT gates, default off), main 45-90d (directional),
    LEAPS 180d+ (stock replacement for hold-strategy names). Earnings bucket needs a calendar.
Rules baked in (sources in README): no naked buys when imp/real>1.5; deep-OTM short-dated
only past lottery gates (EV>=-10%, imp/real<=1.3, spread<=10%, premium<=1% capital).
Data: yfinance option chains (free). Honest limits: no options history; EV assumes history rhymes.
"""
import datetime
import math
import statistics

from .indicators import sma  # noqa: F401  (kept for parity)


def realized_vol_series(C, w):
    out = []
    for i in range(w, len(C)):
        rets = [math.log(C[k] / C[k - 1]) for k in range(i - w + 1, i + 1)]
        out.append(statistics.pstdev(rets) * math.sqrt(252) * 100)
    return out

def move_dist(C, T):
    return [(C[i + T] / C[i] - 1) * 100 for i in range(len(C) - T)]

def score_call(S, K, P, ups):
    """Empirical EV. De-trended: subtract the historical mean drift so a 10x bull-run
    history doesn't inflate call EV (survivorship/trend bias) — keeps only the vol structure."""
    if not ups or P <= 0:
        return None
    mu = statistics.mean(ups)
    ups = [r - mu for r in ups]
    payoffs = [max(0.0, S * (1 + r / 100) - K) for r in ups]
    ev = statistics.mean(payoffs) - P
    pwin = sum(1 for r in ups if S * (1 + r / 100) - K > P) / len(ups) * 100
    return {"EV_pct": round(ev / P * 100), "P_win": round(pwin),
            "breakeven_move": round(((K + P) / S - 1) * 100, 1)}

def _mid(row):
    b, a = float(row.get("bid") or 0), float(row.get("ask") or 0)
    if b > 0 and a > 0:
        return (b + a) / 2, (a - b) / ((b + a) / 2) * 100
    lp = float(row.get("lastPrice") or 0)
    return (lp, None) if lp > 0 else (None, None)

def top_contracts(watchlist, get_bars, capital=10000, max_tickers=12, top=10):
    """Daily Top-10 buy-worthy options across the whole pool — ranked by de-trended
    empirical EV using REAL chain quotes, and shown even if everything is expensive
    (a 'least bad' ranking beats no ranking; the gates still apply before any trade)."""
    cands = []
    for t in watchlist[:max_tickers]:
        try:
            bars = get_bars(t)
            if not bars or len(bars) < 300:
                continue
            a = assess_options(t, bars, capital)
            for b in a.get("buckets", []):
                if b.get("EV_pct") is None:
                    continue
                cands.append({"t": t, "bucket": b["bucket"], "expiry": b["expiry"],
                              "dte": b["dte"], "K": b["strike"], "mid": b["mid"],
                              "spread_pct": b.get("spread_pct"), "EV_pct": b["EV_pct"],
                              "P_win": b["P_win"], "gates": b.get("gates", []),
                              "lottery_admitted": b.get("lottery_admitted")})
        except Exception:
            continue
    cands.sort(key=lambda x: -x["EV_pct"])
    return cands[:top]


def assess_options(ticker, bars, capital=10000):
    """Vol cone + bucket-by-bucket contract candidates via yfinance chains."""
    C = [b["c"] for b in bars]
    S = C[-1]
    out = {"ticker": ticker, "spot": round(S, 2), "buckets": [], "notes": []}
    if len(C) < 300:
        out["notes"].append("history too short for cone"); return out
    rv21 = realized_vol_series(C, 21)
    real21 = statistics.median([abs(m) for m in move_dist(C, 21)])
    out["realized_median_21d"] = round(real21, 1)
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        expiries = tk.options or []
    except Exception as e:
        out["notes"].append(f"chain unavailable: {e}"); return out
    today = datetime.date.today()
    def pick(lo, hi):
        for e in expiries:
            d = (datetime.date.fromisoformat(e) - today).days
            if lo <= d <= hi:
                return e, d
        return None, None
    # implied move from ~21d ATM straddle
    e21, d21 = pick(14, 35)
    if e21:
        try:
            ch = tk.option_chain(e21)
            calls = ch.calls; puts = ch.puts
            k_atm = min(calls["strike"], key=lambda k: abs(k - S))
            cm, _ = _mid(calls[calls.strike == k_atm].iloc[0].to_dict())
            pm, _ = _mid(puts[puts.strike == k_atm].iloc[0].to_dict())
            if cm and pm:
                imp = (cm + pm) / S * 100 * math.sqrt(21 / max(d21, 1))
                out["implied_move_21d"] = round(imp, 1)
                out["imp_vs_real"] = round(imp / real21, 2) if real21 else None
                out["verdict"] = ("cheap" if imp / real21 < 0.85 else
                                  "rich" if imp / real21 > 1.15 else "fair")
        except Exception as e:
            out["notes"].append(f"implied move failed: {e}")
    ir = out.get("imp_vs_real")
    # bucket candidates
    for name, lo, hi, otm_pct in [("main_45_90d", 45, 95, 0.0), ("main_otm5", 45, 95, 0.05),
                                  ("lottery_7_21d", 7, 21, 0.12), ("leaps_180d+", 170, 500, -0.15)]:
        e, d = pick(lo, hi)
        if not e:
            continue
        try:
            calls = tk.option_chain(e).calls
            k = min(calls["strike"], key=lambda x: abs(x - S * (1 + otm_pct)))
            row = calls[calls.strike == k].iloc[0].to_dict()
            mid, spr = _mid(row)
            if not mid:
                continue
            sc = score_call(S, float(k), mid, move_dist(C, min(d, len(C) // 3)))
            item = {"bucket": name, "expiry": e, "dte": d, "strike": float(k),
                    "mid": round(mid, 2), "spread_pct": round(spr) if spr else None, **(sc or {})}
            # gates
            gates = []
            if ir and ir > 1.5 and "leaps" not in name:
                gates.append("vol-tax>1.5 → 只用价差,不裸买")
            if name.startswith("lottery"):
                ok = (sc and sc["EV_pct"] >= -10) and (not ir or ir <= 1.3) and \
                     (spr is None or spr <= 10) and mid * 100 <= capital * 0.01
                item["lottery_admitted"] = bool(ok)
                if not ok:
                    gates.append("彩票准入未过 → 不推荐")
            item["gates"] = gates
            out["buckets"].append(item)
        except Exception:
            continue
    return out
