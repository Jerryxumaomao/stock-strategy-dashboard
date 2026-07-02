"""
Orchestrator: read config -> fetch history (data source) -> diagnose every ticker ->
render a self-contained dashboard.html (data embedded, opens with file://).
"""
import json
import os
import time

from .datasource import get_history
from .diagnose import diagnose

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(path=None):
    path = path or os.path.join(ROOT, "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build(config=None, source=None, period="5y", verbose=True):
    cfg = config or load_config()
    source = source or cfg.get("source", "yahoo")
    tickers = cfg.get("watchlist", [])
    results = []
    for t in tickers:
        try:
            bars = get_history(t, source=source, period=period)
            if not bars:
                if verbose: print(f"  {t}: no data, skipped")
                continue
            rec = diagnose(t, bars)
            results.append(rec)
            if verbose:
                print(f"  {t}: {rec['strategy']:8} {rec.get('bucket','')}  ({rec['stage']}, vol {rec['vol']}%)")
        except Exception as e:
            if verbose: print(f"  {t}: ERROR {e}")
        time.sleep(0.2)  # be polite to the data source
    render(results, cfg)
    return results


STRAT_LABEL = {"dip": "📉宜抄底", "dip_re": "📉抄底+再进", "brk": "📈宜突破",
               "brk_atr": "📈突破·宽止损", "avoid": "🚫回避"}


def render(results, cfg):
    tmpl_path = os.path.join(ROOT, "dashboard_template.html")
    with open(tmpl_path, encoding="utf-8") as f:
        tmpl = f.read()
    payload = {"title": cfg.get("title", "Stock Strategy Dashboard"),
               "as_of": time.strftime("%Y-%m-%d %H:%M"),
               "source": cfg.get("source", "yahoo"),
               "tickers": results}
    html = tmpl.replace("/*__DATA__*/", json.dumps(payload, ensure_ascii=False))
    out = os.path.join(ROOT, "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n[ok] dashboard -> {out}  ({len(results)} tickers)")
    # summary
    from collections import Counter
    c = Counter(r["strategy"] for r in results)
    print("[strategy] " + " · ".join(f"{STRAT_LABEL.get(k,k)}:{v}" for k, v in c.items()))
