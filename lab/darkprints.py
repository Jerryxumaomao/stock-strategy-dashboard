#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
暗盘 prints 抓取(TWS Time & Sales 同源): 通过本地 TWS API 拉当日逐笔,
过滤 FINRA/ADF(暗盘/场外)成交 → 大单榜 + 价格聚集档位。
前置(一次性): TWS -> File -> Global Configuration -> API -> Settings ->
  勾选 Enable ActiveX and Socket Clients, 端口 7496(实盘)/7497(模拟), 取消 Read-Only 可不必。
运行时 TWS 必须开着。未连接则优雅跳过(看板显示设置提示)。
"""
import json, os, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
def _watch():
    import json, os
    cfg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    try: return json.load(open(cfg, encoding="utf-8")).get("watchlist", [])[:8]
    except Exception: return []
TICKERS = _watch()  # 自选池前8只
DARK_EX = {"FINRA", "ADF", "D", "DARK"}
MIN_NOTIONAL = 100_000  # 大单门槛 $10万

def main():
    from ib_insync import IB, Stock
    ib = IB()
    for port in (7496, 7497, 4001, 4002):
        try:
            ib.connect('127.0.0.1', port, clientId=27, timeout=4); break
        except Exception:
            continue
    if not ib.isConnected():
        json.dump({'status': 'no_tws'}, open(os.path.join(BASE, 'darkprints.json'), 'w'))
        print('未连接 TWS(需开启 API,见脚本头部说明)'); return
    out = {'status': 'ok', 'as_of': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'), 'prints': [], 'levels': {}}
    for t in TICKERS:
        try:
            c = Stock(t, 'SMART', 'USD'); ib.qualifyContracts(c)
            ticks = ib.reqHistoricalTicks(c, '', datetime.datetime.now(), 1000, 'TRADES', useRth=False)
            lv = {}
            for k in ticks:
                ex = (getattr(k, 'exchange', '') or '').upper()
                if not any(d in ex for d in DARK_EX): continue
                notional = k.price * k.size
                px_bin = round(k.price, 0 if k.price > 100 else 1)
                lv[px_bin] = lv.get(px_bin, 0) + k.size
                if notional >= MIN_NOTIONAL:
                    out['prints'].append({'t': t, 'time': k.time.strftime('%H:%M:%S'),
                                          'px': k.price, 'size': int(k.size),
                                          'usd_k': round(notional / 1000)})
            if lv:
                top = sorted(lv.items(), key=lambda x: -x[1])[:3]
                out['levels'][t] = [{'px': p, 'vol': int(v)} for p, v in top]
        except Exception:
            continue
    ib.disconnect()
    out['prints'].sort(key=lambda x: -x['usd_k']); out['prints'] = out['prints'][:20]
    json.dump(out, open(os.path.join(BASE, 'darkprints.json'), 'w'), ensure_ascii=False)
    print(f"暗盘prints {len(out['prints'])} 笔大单 · 档位 {len(out['levels'])} 票")

if __name__ == '__main__':
    main()
