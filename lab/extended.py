#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 盘前/盘后/夜盘实时报价(TWS API, useRTH=False 数据源): 每次刷新时若处于延长时段,
# 抓自选核心票延长时段价 vs 昨收 -> extended.json。诚实: 期权延长时段基本不交易(只能动正股);
# 延长时段点差宽、流动性薄, 一律限价单; IBKR夜盘(IBEOS)仅部分标的。
import json, os, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
def _watch():
    import json as _j, os as _o
    cfg = _o.path.join(_o.path.dirname(_o.path.dirname(_o.path.abspath(__file__))), "config.json")
    try: return _j.load(open(cfg, encoding="utf-8")).get("watchlist", [])[:10]
    except Exception: return []
TICKERS = _watch()

def session_now():
    # 以美东时间判断时段
    try:
        from zoneinfo import ZoneInfo
        et = datetime.datetime.now(ZoneInfo('America/New_York'))
    except Exception:
        et = datetime.datetime.utcnow() - datetime.timedelta(hours=4)
    hm = et.hour * 60 + et.minute
    if et.weekday() >= 5: return 'weekend', et
    if 4 * 60 <= hm < 9 * 60 + 30: return 'premarket', et
    if 9 * 60 + 30 <= hm < 16 * 60: return 'rth', et
    if 16 * 60 <= hm < 20 * 60: return 'afterhours', et
    return 'overnight', et

def main():
    sess, et = session_now()
    out = {'status': 'ok', 'session': sess, 'as_of': et.strftime('%Y-%m-%d %H:%M ET'), 'rows': []}
    from ib_insync import IB, Stock
    ib = IB()
    for port in (7496, 7497, 4001, 4002):
        try: ib.connect('127.0.0.1', port, clientId=28, timeout=4); break
        except Exception: continue
    if not ib.isConnected():
        json.dump({'status': 'no_tws', 'session': sess}, open(os.path.join(BASE, 'extended.json'), 'w'))
        print('未连接TWS'); return
    for t in TICKERS:
        try:
            c = Stock(t, 'SMART', 'USD'); ib.qualifyContracts(c)
            tk = ib.reqMktData(c, '', False, False)
            ib.sleep(2.5)
            px = tk.last or tk.markPrice() or None
            prev = tk.close
            if px and prev and px == px and prev == prev:  # 过滤 NaN(休市无流)
                out['rows'].append({'t': t, 'px': round(px, 2), 'prev': round(prev, 2),
                                    'chg': round((px / prev - 1) * 100, 2)})
            ib.cancelMktData(c)
        except Exception:
            continue
    ib.disconnect()
    out['rows'].sort(key=lambda r: -abs(r['chg']))
    json.dump(out, open(os.path.join(BASE, 'extended.json'), 'w'), ensure_ascii=False)
    print(f"[{sess}] {len(out['rows'])} 票延长时段报价")

if __name__ == '__main__':
    main()
