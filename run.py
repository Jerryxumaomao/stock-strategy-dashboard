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
    print("== 初始化 == 输入你要盯的股票代码,空格或逗号分隔(如: NVDA AMD MU TSM):")
    raw = input("> ").replace(",", " ").split()
    tickers = [t.strip().upper() for t in raw if t.strip()]
    if not tickers:
        print("未输入,退出。"); return
    cfg = _cfg(); cfg["watchlist"] = sorted(set(tickers)); _save(cfg)
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
    else: print(__doc__)


if __name__ == "__main__":
    main()
