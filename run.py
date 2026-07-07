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
  python run.py top10                daily Top-10 buy-worthy options across the pool (real quotes)
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
    elif cmd == "top10":
        from lab.options import top_contracts
        from lab.datasource import get_history as gh
        cfg = _cfg()
        rows = top_contracts(cfg.get("watchlist", []), lambda t: gh(t, source=cfg.get("source", "yahoo")), cfg.get("capital", 10000))
        print("每日Top10期权(真实链报价·去趋势EV排序·即使全贵也排最不差):")
        for i, r in enumerate(rows):
            print(f" #{i+1} {r['t']:6} {r['bucket']:12} {r['expiry']} K={r['K']} mid=${r['mid']} EV{r['EV_pct']}% 胜率{r['P_win']}% "
                  + ("⛔" + ";".join(r['gates']) if r['gates'] else "✅门控通过"))
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
    elif cmd == "ashare":  # A股情报: 情绪周期 + 北向 + 龙虎榜(见 docs/A股量化知识手册.md)
        from lab import ashare as A
        print("== 市场情绪周期(涨停家数/连板/炸板率) ==")
        print("  ", A.sentiment_gauge())
        print("== 北向资金(近10日净流入,亿元) ==")
        nb = A.northbound_flow()
        if isinstance(nb, list):
            for r in nb: print(f"  {r['date']}  {r['net_in_yi']:+.1f}亿")
        else: print("  ", nb)
        print("== 龙虎榜(今日) ==")
        lhb = A.dragon_tiger()
        if isinstance(lhb, list):
            for r in lhb[:15]: print("  ", r)
        else: print("  ", lhb)
    elif cmd == "screen":  # A股选股筛选器: run.py screen [价格下限 上限] [涨跌下限 上限]
        from lab.ashare_extras import screener
        a = [float(x) for x in args] if args else []
        kw = {}
        if len(a) >= 2: kw["price"] = (a[0], a[1])
        if len(a) >= 4: kw["chg"] = (a[2], a[3])
        kw.setdefault("min_amount_yi", 5)
        sc = screener(**kw)
        if "error" in sc: print(sc["note"]); return
        print(f"全A {sc['n_universe']} 只 → 命中 {sc['n_hit']} 只(按成交额):")
        for r in sc["rows"]: print(f"  {r['code']} {r['name']:8} {r['px']:>8} {r['chg_pct']:>+6}%  成交{r['amount_yi']}亿")
    elif cmd == "dossier":  # 个股档案: run.py dossier 600519
        from lab.ashare_extras import stock_dossier
        for c in (args or ["600519"]):
            d = stock_dossier(c)
            print(f"== {d['code']} 档案 ==")
            if d.get("pe_ttm"): print(f"  PE(TTM) {d['pe_ttm']['now']} [近一年{d['pe_ttm']['pct_1y']}分位·{d['pe_ttm']['tag']}]")
            if d.get("pb"): print(f"  PB {d['pb']['now']} [近一年{d['pb']['pct_1y']}分位·{d['pb']['tag']}]")
            for k, v in (d.get("financials") or {}).items(): print(f"  {k}: {v}")
    elif cmd == "rotation":  # 行业轮动
        from lab.ashare_extras import industry_rotation
        ir = industry_rotation()
        if "error" in ir: print(ir["note"]); return
        print("领涨板块:", "  ".join(f"{r['industry']}{r['chg_pct']:+}%" for r in ir["领涨"]))
        print("领跌板块:", "  ".join(f"{r['industry']}{r['chg_pct']:+}%" for r in ir["领跌"]))
        print(ir["note"])
    elif cmd == "lhb":  # 龙虎榜因子
        from lab.ashare_extras import lhb_factor
        lf = lhb_factor(period=(args[0] if args else "近一月"))
        if "error" in lf: print(lf["note"]); return
        print(f"龙虎榜净买额榜({lf['period']}, 共{lf['n']}只):")
        for r in lf["净买额榜"][:20]: print(f"  {r['code']} {r['name']:8} 净买{r['净买额']}亿 · 上榜{r['上榜次数']}次")
        print(lf["note"])
    elif cmd == "events":  # 事件风险
        from lab.ashare_extras import event_risk
        ev = event_risk()
        jj = ev.get("解禁", {})
        if isinstance(jj, dict) and "error" not in jj:
            for k, rows in jj.items():
                if k == "note": continue
                print(f"== 解禁({k}) =="); [print("  ", r) for r in rows[:12]]
        else: print("解禁:", jj)
        print("市场质押:", ev.get("市场质押"))
    elif cmd == "review-cn":  # A股盘后复盘(市场宽度+情绪)
        from lab.ashare_extras import market_review
        mr = market_review()
        print("市场宽度:", mr.get("市场宽度"))
        print("情绪周期:", mr.get("情绪周期"))
    elif cmd == "daban":  # 打板: 扫自选当前首板/连板 + 打板胜率与尾部风险回测
        from lab import daban as DB
        from lab.ashare import board_and_limit
        cfg = _cfg(); src = cfg.get("source", "akshare")
        print("⚠️ 打板是A股最高风险流派,散户多亏(次日高开低走);以下仅供认识风险,非鼓励打板。\n")
        print("== 自选当前打板状态 ==")
        for t in cfg.get("watchlist", []):
            try:
                b = get_history(t, source=src)
                lim = board_and_limit(t, "")["limit_pct"] / 100
                sc = DB.daban_scan(b, lim, "")
                if sc.get("state") not in ("无", "数据不足"):
                    print(f"  {t}: [{sc['state']}] {sc.get('signal', '')}")
            except Exception:
                continue
        print("\n== 打板胜率回测(样例池,看尾部风险不是均值) ==")
        for t in (args or cfg.get("watchlist", [])[:5]):
            try:
                b = get_history(t, source=src)
                lim = board_and_limit(t, "")["limit_pct"] / 100
                bt = DB.daban_backtest(b, lim, "all")
                if bt["n"] >= 5:
                    flag = " ⚠️小样本" if bt.get("小样本存疑") else ""
                    print(f"  {t}: {bt['n']}次{flag} · 次日均值{bt['次日收盘卖_均值%']}% 胜率{bt['次日收盘卖_胜率%']}% · 次日最差{bt['次日最差%']}% 跌超5%占比{bt['次日跌超5%占比%']}% · 续板率{bt['续板率%']}%")
            except Exception:
                continue
        print("\n" + DB.daban_backtest.__doc__.strip().split("\n")[0])
        print("均值正≠能赚:强封板买不进(能成交的偏弱=幸存者偏差)、退潮期反转、未含滑点。务必配合 review-cn 看情绪周期。")
    else: print(__doc__)


if __name__ == "__main__":
    main()
