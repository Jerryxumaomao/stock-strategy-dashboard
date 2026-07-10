"""
Orchestrator: fetch -> pool stats (shrinkage prior) -> diagnose every ticker ->
market gate (SPY 200MA) + correlation clusters + dark-pool SVR -> render dashboard ->
freeze + snapshot + review loop.
"""
import json
import math
import os
import statistics
import time

from .datasource import get_history
from .diagnose import diagnose

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path=None):
    path = path or os.path.join(ROOT, "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


STRAT_LABEL = {"dip": "📉宜抄底", "dip_re": "📉抄底+再进", "brk": "📈宜突破",
               "brk_atr": "📈突破·宽止损", "hold": "🏔️长持", "avoid": "🚫回避"}


def _pool_expectancy(barsmap):
    """Pooled per-strategy expectancy — the empirical-Bayes prior for shrinkage.
    Per-ticker samples are small (5-30 trades); shrinking toward the pool mean stops
    a single lucky trade from flipping a ticker's strategy assignment."""
    from .backtest import dip_trades, brk_trades, brk_atr_trades
    pool = {"dip": [], "dip_re": [], "brk": [], "brk_atr": []}
    for t, b in barsmap.items():
        if len(b) < 250:
            continue
        pool["dip"] += dip_trades(b); pool["dip_re"] += dip_trades(b, True)
        pool["brk"] += brk_trades(b); pool["brk_atr"] += brk_atr_trades(b)
    return {k: (statistics.mean([x["R"] for x in v]) if v else 0) for k, v in pool.items()}


def _clusters(barsmap, thr=0.7, win=120):
    rets = {t: [b[i]["c"] / b[i-1]["c"] - 1 for i in range(len(b) - win, len(b))]
            for t, b in barsmap.items() if len(b) >= win + 1}
    ts = sorted(rets); parent = {t: t for t in ts}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def corr(a, b):
        ma, mb = statistics.mean(a), statistics.mean(b)
        num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        da = math.sqrt(sum((x - ma) ** 2 for x in a)); db = math.sqrt(sum((y - mb) ** 2 for y in b))
        return num / (da * db) if da and db else 0
    for i in range(len(ts)):
        for j in range(i + 1, len(ts)):
            if corr(rets[ts[i]], rets[ts[j]]) > thr:
                parent[find(ts[i])] = find(ts[j])
    groups = {}
    for t in ts:
        groups.setdefault(find(t), []).append(t)
    return sorted([v for v in groups.values() if len(v) >= 2], key=len, reverse=True)


def build(config=None, source=None, period="5y", verbose=True):
    cfg = config or load_config()
    source = source or cfg.get("source", "yahoo")
    tickers = cfg.get("watchlist", [])
    barsmap = {}
    for t in tickers:
        try:
            b = get_history(t, source=source, period=period)
            if b:
                barsmap[t] = b
            elif verbose:
                print(f"  {t}: no data, skipped")
        except Exception as e:
            if verbose: print(f"  {t}: ERROR {e}")
        time.sleep(0.2)
    pool_E = _pool_expectancy(barsmap)
    if verbose:
        print("[pool] strategy priors:", {k: round(v, 2) for k, v in pool_E.items()})
    results = []
    for t, b in barsmap.items():
        rec = diagnose(t, b, pool_E=pool_E)
        results.append(rec)
        if verbose:
            print(f"  {t}: {rec['strategy']:8} {rec.get('bucket','')}  ({rec['stage']}, vol {rec['vol']}%)")
    extras = {}
    try:  # SPY 200MA market gate (Faber): below the line -> no breakout chasing, half size
        sb = get_history("SPY", source=source, period=period)
        SC = [x["c"] for x in sb]
        if len(SC) >= 200:
            s200 = sum(SC[-200:]) / 200
            extras["market"] = {"spy": round(SC[-1], 2), "sma200": round(s200, 2),
                                "above": SC[-1] > s200, "pct": round((SC[-1] / s200 - 1) * 100, 1)}
    except Exception as e:
        if verbose: print("[market] skipped:", e)
    try:  # correlation clusters: same cluster ~= same bet, cap 1-2 positions per cluster
        extras["clusters"] = _clusters(barsmap)
    except Exception:
        pass
    try:  # earnings radar (free yfinance, next 3 weeks)
        from .earnings import get_earnings
        extras["earnings"] = get_earnings(tickers)
        if verbose: print(f"[earnings] {len(extras['earnings'])} upcoming in 3 weeks")
    except Exception as e:
        if verbose: print("[earnings] skipped:", e)
    if cfg.get("top10", False):  # daily Top-10 options (real chain quotes; slower — opt-in)
        try:
            from .options import top_contracts
            extras["top10"] = top_contracts(tickers, lambda t: barsmap.get(t), cfg.get("capital", 10000))
            if verbose: print(f"[top10] {len(extras['top10'])} contracts ranked")
        except Exception as e:
            if verbose: print("[top10] skipped:", e)
    try:  # FINRA dark-pool SVR radar (free)
        from .darkpool import dark_svr
        dp = dark_svr(tickers)
        if dp: extras["dark"] = {"as_of": dp["as_of"], "rows": dp["rows"][:15]}
        if verbose: print("[dark] FINRA SVR scanned" if dp else "[dark] no data")
    except Exception as e:
        if verbose: print("[dark] skipped:", e)
    render(results, cfg, extras, barsmap=barsmap)
    try:
        from .review import freeze, run_review
        print("[freeze]", freeze(results, ROOT, spy_last=(extras.get("market") or {}).get("spy")))
        run_review(cfg, ROOT, do_snapshot=True)
    except Exception as e:
        print("[review] skipped:", e)
    return results


def render(results, cfg, extras=None, barsmap=None):
    tmpl_path = os.path.join(ROOT, "dashboard_template.html")
    with open(tmpl_path, encoding="utf-8") as f:
        tmpl = f.read()
    extras = dict(extras or {})
    if cfg.get("movers", True):
        try:
            from .movers import get_movers
            extras["movers"] = get_movers()
            print("[movers] market radar scanned")
        except Exception as e:
            print("[movers] skipped:", e)
    # 私人 DATA schema 装配(信号灯/操作行/复盘/评分与私人看板同一渲染层;缺数据模块留空→标灰)
    from .engines import assemble_payload
    payload = assemble_payload(results, cfg, extras, barsmap or {})
    # Replace the WHOLE marker including its {} placeholder — swapping only the comment
    # leaves `{json}{}` behind, a SyntaxError that renders the dashboard blank.
    html = tmpl.replace("/*__DATA__*/{}", json.dumps(payload, ensure_ascii=False))
    if "/*__DATA__*/" in html:
        raise RuntimeError("payload marker not replaced — template must contain /*__DATA__*/{}")
    out = os.path.join(ROOT, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    hist = os.path.join(ROOT, "history")
    os.makedirs(hist, exist_ok=True)
    with open(os.path.join(hist, "build.log"), "a", encoding="utf-8") as lf:
        # On-disk verification record: "when did the last good build happen" must be
        # answerable from this file, not from anyone's conversation memory.
        lf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} | ok | {len(results)} tickers\n")
    print(f"\n[ok] dashboard -> {out}  ({len(results)} tickers)")
    from collections import Counter
    c = Counter(r["strategy"] for r in results)
    print("[strategy] " + " · ".join(f"{STRAT_LABEL.get(k, k)}:{v}" for k, v in c.items()))
