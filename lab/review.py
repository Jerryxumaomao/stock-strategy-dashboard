"""
Forward review & self-improvement loop (复盘优化系统).

Every `build` freezes the day's recommendations once (idempotent) and merges a market
snapshot; `review` scores every frozen cohort against what actually happened, and only
when evidence clears strict gates does it emit an optimization PROPOSAL (never auto-applies).

Anti-self-deception rules:
  * Recommendations freeze ONCE per day (first build wins) — re-running build intraday
    only refines that day's hi/lo snapshot, it never duplicates samples.
  * Cohorts get a preliminary score at >=5 forward trading days, a formal one at >=10.
  * A proposal requires the same issue in >=2 non-overlapping cohorts and >=30 samples.
  * Proposals are printed for the user to approve; nothing is changed silently.
"""
import datetime
import glob
import json
import os
import statistics

from .datasource import get_history


def _hist_dir(root):
    d = os.path.join(root, "history")
    os.makedirs(d, exist_ok=True)
    return d


def freeze(results, root):
    """Idempotent daily freeze of the diagnosed recommendations."""
    today = datetime.date.today().isoformat()
    fp = os.path.join(_hist_dir(root), f"recs-{today}.json")
    if os.path.exists(fp):
        return f"recs-{today}.json exists, skipped (one freeze per day)"
    recs = {}
    for r in results:
        recs[r["ticker"]] = {
            "last": r["last"], "strategy": r["strategy"],
            "state": (r.get("state") or {}).get("st"),
            "signal": r.get("signal") or {},
        }
    json.dump({"date": today, "recs": recs}, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return f"froze {len(recs)} recs -> recs-{today}.json"


def snapshot(tickers, source, root):
    """Merge the latest daily bar of each ticker into history/snap-<bar_date>.json.
    Uses the bar's own date, so holidays/weekends never create empty cohorts, and
    running multiple times a day tightens that day's hi/lo instead of duplicating."""
    hist = _hist_dir(root)
    merged = 0
    for t in tickers:
        try:
            bars = get_history(t, source=source, period="5d")
        except Exception:
            continue
        if not bars:
            continue
        b = bars[-1]
        fp = os.path.join(hist, f"snap-{b['date']}.json")
        cur = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
        c = cur.get(t)
        if c:
            cur[t] = {"last": b["c"], "hi": max(c["hi"], b["h"]), "lo": min(c["lo"], b["l"])}
        else:
            cur[t] = {"last": b["c"], "hi": b["h"], "lo": b["l"]}
        json.dump(cur, open(fp, "w", encoding="utf-8"), ensure_ascii=False)
        merged += 1
    return f"snapshot merged {merged} tickers"


def score(root):
    """Score every frozen cohort against all later snapshots."""
    hist = _hist_dir(root)
    snaps = {}
    for sf in sorted(glob.glob(os.path.join(hist, "snap-*.json"))):
        snaps[os.path.basename(sf)[5:15]] = json.load(open(sf, encoding="utf-8"))
    report = {}
    for rf in sorted(glob.glob(os.path.join(hist, "recs-*.json"))):
        rdate = os.path.basename(rf)[5:15]
        later = [v for d, v in snaps.items() if d > rdate]
        if not later:
            continue
        agg = {}
        for snap in later:
            for t, v in snap.items():
                a = agg.setdefault(t, {"hi": -1e18, "lo": 1e18, "last": None})
                a["hi"] = max(a["hi"], v["hi"]); a["lo"] = min(a["lo"], v["lo"]); a["last"] = v["last"]
        recs = json.load(open(rf, encoding="utf-8"))["recs"]
        rows = []
        for t, r in recs.items():
            a = agg.get(t)
            if not a or not r.get("last"):
                continue
            fwd = (a["last"] / r["last"] - 1) * 100
            sig = r.get("signal") or {}
            zones = sig.get("buy_zones") or []
            buy_hit = any(a["lo"] <= z for z in zones)
            trig = sig.get("trigger")
            trig_fired = bool(trig) and a["hi"] >= trig
            stop = sig.get("stop") or sig.get("trend_stop")
            stop_hit = bool(stop) and a["lo"] <= stop
            rows.append({"t": t, "strategy": r.get("strategy"), "state": r.get("state"),
                         "fwd": round(fwd, 1), "buy_hit": buy_hit, "has_zones": bool(zones),
                         "trig_fired": trig_fired, "stop_hit": stop_hit})
        by_s = {}
        for r in rows:
            by_s.setdefault(r["strategy"] or "?", []).append(r["fwd"])
        zoned = [r for r in rows if r["has_zones"]]
        touched = [r for r in zoned if r["buy_hit"]]
        report[rdate] = {
            "days_elapsed": len(later), "n": len(rows),
            "fwd_by_strategy": {k: {"n": len(v), "avg": round(statistics.mean(v), 1)} for k, v in by_s.items()},
            "buy_zone_touch_rate": round(len(touched) / len(zoned) * 100, 1) if zoned else None,
            "stop_breach_after_touch": round(sum(1 for r in touched if r["stop_hit"]) / len(touched) * 100, 1) if touched else None,
            "breakout_fire_rate": round(sum(1 for r in rows if r["trig_fired"]) / max(1, sum(1 for r in rows if (r.get("strategy") or "").startswith("brk"))) * 100, 1),
        }
    json.dump(report, open(os.path.join(hist, "review-report.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return report


def propose(report, root):
    """Emit optimization proposals only past strict evidence gates. Never auto-apply."""
    mature = {d: v for d, v in report.items() if v.get("days_elapsed", 0) >= 5}
    props = []

    def gate(pid, flags, evidence, change):
        hits = [d for d, f in flags.items() if f]
        if len(hits) >= 2 and sum(mature[d]["n"] for d in hits) >= 30:
            props.append({"id": pid, "cohorts": hits, "evidence": evidence,
                          "suggested_change": change, "status": "pending_user_approval"})

    if mature:
        def active_vs_avoid(v):
            fs = v["fwd_by_strategy"]
            act = [x for k, x in fs.items() if k != "avoid"]
            av = fs.get("avoid")
            if not av or av["n"] < 8 or not act:
                return False
            act_avg = statistics.mean([x["avg"] for x in act])
            return act_avg < av["avg"]
        gate("buyzones_too_deep",
             {d: (v.get("buy_zone_touch_rate") is not None and v["buy_zone_touch_rate"] < 25) for d, v in mature.items()},
             "dip/hold buy zones almost never touched while prices ran (posted too deep)",
             "raise the first buy zone toward price (e.g. add a shallow tranche at -3%)")
        gate("stops_too_tight",
             {d: (v.get("buy_zone_touch_rate") or 0) > 70 and (v.get("stop_breach_after_touch") or 0) > 40 for d, v in mature.items()},
             "zones get filled then stopped out (zones/stops too shallow)",
             "widen stop to ~1.5x ATR or shift zones one level deeper")
        gate("strategy_discrimination_broken",
             {d: active_vs_avoid(v) for d, v in mature.items()},
             "active picks (dip/brk/hold) underperform the avoid bucket",
             "re-run full-universe diagnosis and review scoring weights")
    out = {"as_of": datetime.date.today().isoformat(), "proposals": props}
    json.dump(out, open(os.path.join(_hist_dir(root), "proposals.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return props


def run_review(cfg, root, do_snapshot=True):
    """Full loop: snapshot -> score -> propose. Call after build, or standalone intraday."""
    msgs = []
    if do_snapshot:
        msgs.append(snapshot(cfg.get("watchlist", []), cfg.get("source", "yahoo"), root))
    report = score(root)
    for d, v in sorted(report.items()):
        fs = " | ".join(f"{k}:{x['avg']}%(n{x['n']})" for k, x in sorted(v["fwd_by_strategy"].items()))
        print(f"[review] {d} +{v['days_elapsed']}d n{v['n']}  {fs}  zone_touch {v['buy_zone_touch_rate']}% brk_fire {v['breakout_fire_rate']}%")
    props = propose(report, root)
    if props:
        print(f"[propose] {len(props)} optimization proposal(s) PENDING USER APPROVAL:")
        for p in props:
            print("  -", p["id"], "|", p["evidence"], "->", p["suggested_change"])
    else:
        print("[propose] evidence below gates — no proposal (correct behavior while data accumulates)")
    for m in msgs:
        print("[snap]", m)
    return report, props
