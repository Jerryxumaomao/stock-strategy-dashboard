"""
Execution audit (纪律分): score the user's REAL trades against the frozen recommendations
and the options rules. The biggest leak for most retail traders is execution drift, not
signal quality — this makes it a weekly number.

Trades file format (history/trades.json), broker-agnostic:
  [{"date":"YYYY-MM-DD","symbol":"NVDA","sec_type":"STK|OPT","side":"BUY|SELL",
    "price":0,"amount":0,"realized_pnl":0, "expiry":"YYYY-MM-DD","strike":0,"spot":0}]
(expiry/strike/spot only for OPT rows; export from your broker or fill by hand.)

Rules: R3 lottery (OPT buy OTM>15% & DTE<30 without admission) · R17 size (premium >5% capital)
     · R_z zone discipline (stock fills within ±3% of a frozen buy/sell zone)
     · R_exit (closing a position the system had flagged = credit, late beats never).
Score: ✅=1 ⚠️=0.5 ❌=0, averaged ×100. Drift cost = realized losses on symbols bought in violation.
"""
import datetime
import glob
import json
import os


def _load_recs(hist):
    out = {}
    for fp in sorted(glob.glob(os.path.join(hist, "recs-*.json"))):
        out[os.path.basename(fp)[5:15]] = json.load(open(fp, encoding="utf-8"))["recs"]
    return out

def _rec_for(recs_all, sym, tdate):
    best = None
    for d, recs in recs_all.items():
        if d <= tdate and sym in recs:
            best = recs[sym]
    return best

def audit_trades(trades, hist_dir, capital=10000):
    recs_all = _load_recs(hist_dir)
    rows = []
    for t in trades:
        sym, side, px = t["symbol"], t["side"], t["price"]
        tdate = t.get("date", "")[:10]
        amt = abs(t.get("amount", 0)); pnl = t.get("realized_pnl", 0)
        v, why = "·", ""
        if t.get("sec_type") == "OPT" and side == "BUY":
            bad = []
            if t.get("expiry") and t.get("strike") and t.get("spot"):
                dte = (datetime.date.fromisoformat(t["expiry"]) - datetime.date.fromisoformat(tdate)).days
                otm = (t["strike"] - t["spot"]) / t["spot"] * 100
                if otm > 15 and dte < 30:
                    bad.append(f"R3 lottery (OTM{otm:.0f}%/{dte}d)")
            if amt > capital * 0.05:
                bad.append(f"R17 size (${amt:.0f} > 5% capital)")
            v, why = ("❌", " + ".join(bad)) if bad else ("✅", "rules ok")
        elif t.get("sec_type") == "OPT":
            rec = _rec_for(recs_all, sym, tdate)
            if rec and rec.get("strategy") == "avoid":
                v, why = "✅", "R_exit: closed a flagged position"
            else:
                v, why = ("⚠️", "loss exit, no frozen basis") if pnl < 0 else ("✅", "profit taken")
        else:
            rec = _rec_for(recs_all, sym, tdate)
            sig = (rec or {}).get("signal") or {}
            zones = sig.get("buy_zones") if side == "BUY" else None
            if zones and any(abs(px - z) / z <= 0.03 for z in zones):
                v, why = "✅", "R_z: hit frozen zone"
            elif rec:
                v, why = "⚠️", "R_z: off-zone fill"
            else:
                v, why = "·", "predates freeze — unscored"
        rows.append({"date": tdate, "sym": sym, "side": side, "px": px,
                     "pnl": round(pnl, 1), "verdict": v, "why": why})
    scored = [r for r in rows if r["verdict"] in "✅⚠️❌"]
    score = round(sum({"✅": 1, "⚠️": .5, "❌": 0}[r["verdict"]] for r in scored) / len(scored) * 100) if scored else None
    bad_syms = {r["sym"] for r in rows if r["verdict"] == "❌" and r["side"] == "BUY"}
    drift = round(sum(r["pnl"] for r in rows if r["sym"] in bad_syms and r["pnl"] < 0))
    return {"discipline_score": score, "drift_cost": drift, "n_scored": len(scored), "rows": rows}
