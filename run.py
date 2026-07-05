#!/usr/bin/env python3
"""
CLI for stock-strategy-dashboard.

  python run.py init                 interactive: enter your watchlist, then build
  python run.py add NVDA MSFT ...    add tickers (each gets diagnosed), then rebuild
  python run.py remove NVDA          drop a ticker, rebuild
  python run.py build                rebuild dashboard from config.json (auto: freeze + review)
  python run.py review               intraday refresh: snapshot + score cohorts + check proposals
  python run.py diagnose NVDA        print one ticker's diagnosis (no dashboard write)
  python run.py options NVDA MU      options: vol cone + implied-vs-realized + 4-bucket candidates
  python run.py audit                score real trades (history/trades.json) vs frozen recs
  python run.py movers               market-wide movers radar: gainers/losers/actives + options UOA
  python run.py darkpool             FINRA dark-pool SVR radar for your watchlist (free, daily)
  python run.py darkprints           today's dark-pool block prints via local TWS API (optional)
  python run.py extended             pre/after-hours & overnight quotes via local TWS API (optional)

Data source defaults to Yahoo Finance (free). Change "source" in config.json.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
CONFIG = os.path.join(ROOT, "config.json")

from lab.build import build, load_config  # noqa: E402
from lab.datasource import get_history     # noqa: E402
from lab.diagnose import diagnose          # noqa: E402


def _save(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _cfg():
    if os.path.exists(CONFIG):
        return load_config()
    return {"title": "Stock Strategy Dashboard", "source": "yahoo", "watchlist": []}


def cmd_init():
    print("== 初始化 · Step 1/2 选择数据源 ==")
    print("  1. yahoo(默认)— 免费、无需账号;行情延迟约15分钟,期权链质量一般")
    print("  2. ibkr — 券商实时数据(含实时期权链/IV/盘口)。质量最佳,但需要券商账户,")
    print("            且实时行情订阅可能产生费用(如 IBKR 的 OPRA/美股包,通常每月几美元)")
    print("  3. tradingview — 同为扩展位,需自行接入")
    print("  提示:2/3 需在 lab/datasource.py 实现接入函数;未接入前建议先用 yahoo 跑通。")
    src = input("选择 1/2/3(回车=1)> ").strip()
    source = {"1": "yahoo", "2": "ibkr", "3": "tradingview", "": "yahoo"}.get(src, "yahoo")
    if source != "yahoo":
        print(f"[注意] 已选 {source}:请在 lab/datasource.py 完成接入;实时行情订阅可能产生券商费用。")
    print("== 初始化 · Step 2/2 输入你要盯的股票代码,空格或逗号分隔(如: NVDA AMD MU TSM):")
    raw = input("> ").replace(",", " ").split()
    tickers = [t.strip().upper() for t in raw if t.strip()]
    if not tickers:
        print("未输入,退出。"); return
    cfg = _cfg(); cfg["watchlist"] = sorted(set(tickers)); cfg["source"] = source; _save(cfg)
    print(f"已保存 {len(cfg['watchlist'])} 只。开始诊断+构建 ...")
    build(cfg)


def cmd_add(args):
    cfg = _cfg()
    add = [t.upper() for t in args]
    cfg["watchlist"] = sorted(set(cfg.get("watchlist", []) + add))
    _save(cfg)
    print(f"已加入 {add},共 {len(cfg['watchlist'])} 只。重新诊断+构建 ...")
    build(cfg)


def cmd_remove(args):
    cfg = _cfg()
    cfg["watchlist"] = [t for t in cfg.get("watchlist", []) if t.upper() not in [a.upper() for a in args]]
    _save(cfg); print("已移除,重建 ..."); build(cfg)


def cmd_diagnose(args):
    src = _cfg().get("source", "yahoo")
    for t in args:
        t = t.upper()
        bars = get_history(t, source=src)
        rec = diagnose(t, bars)
        print(json.dumps(rec, ensure_ascii=False, indent=1))


def main():
    if len(sys.argv) < 2:
        print(__doc__); return
    cmd = sys.argv[1]; args = sys.argv[2:]
    if cmd == "init": cmd_init()
    elif cmd == "add": cmd_add(args)
    elif cmd == "remove": cmd_remove(args)
    elif cmd == "build": build(_cfg())
    elif cmd == "review":
        from lab.review import run_review
        run_review(_cfg(), ROOT, do_snapshot=True)
    elif cmd == "diagnose": cmd_diagnose(args)
    elif cmd == "options":
        from lab.options import assess_options
        cfg = _cfg()
        for t in [a.upper() for a in args] or cfg.get("watchlist", [])[:3]:
            bars = get_history(t, source=cfg.get("source", "yahoo"))
            print(json.dumps(assess_options(t, bars, cfg.get("capital", 10000)), ensure_ascii=False, indent=1))
    elif cmd == "audit":
        from lab.audit import audit_trades
        cfg = _cfg(); hist = os.path.join(ROOT, "history")
        fp = os.path.join(hist, "trades.json")
        if not os.path.exists(fp): print("no history/trades.json — export trades from your broker first"); return
        rep = audit_trades(json.load(open(fp, encoding="utf-8")), hist, cfg.get("capital", 10000))
        print(f"纪律分 {rep['discipline_score']}/100 · scored {rep['n_scored']} · drift ${rep['drift_cost']}")
        for r in rep["rows"]: print(" ", r["date"], r["verdict"], r["sym"], r["side"], r["px"], r["why"], f"(pnl {r['pnl']})")
    elif cmd == "darkpool":
        from lab.darkpool import dark_svr
        dp = dark_svr(_cfg().get("watchlist", []))
        if not dp: print("no FINRA data"); return
        print("dark-pool SVR", dp["as_of"], "(z>=|1.5| = anomaly; high SVR ~= buying pressure)")
        for r in dp["rows"][:15]: print(f"  {r['t']:6} SVR {r['svr']}% (avg {r['avg10']}%) z={r['z']}")
    elif cmd == "darkprints":
        import subprocess as sp
        sp.run([sys.executable, os.path.join(ROOT, "lab", "darkprints.py")])
    elif cmd == "extended":
        import subprocess as sp
        sp.run([sys.executable, os.path.join(ROOT, "lab", "extended.py")])
    elif cmd == "movers":
        from lab.movers import get_movers
        m = get_movers()
        for k in ["day_gainers", "day_losers", "most_actives"]:
            rows = m["movers"].get(k)
            print(f"== {k} ==")
            if isinstance(rows, list):
                for r in rows[:10]: print(f"  {r['s']:6} {r['chg']:>6}%  volx {r['volx']}  ${r['px']}  {r['n']}")
            else: print(" ", rows)
        print("== options UOA (vol>=3x OI) ==")
        for u in m["uoa"]: print(f"  {u['t']:6} {u['kind']} {u['expiry']} ${u['k']}  vol {u['vol']} / oi {u['oi']} = {u['ratio']}x  ${u['prem_m']}M")
    else: print(__doc__)


if __name__ == "__main__":
    main()
