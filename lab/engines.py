# -*- coding: utf-8 -*-
"""
engines.py — 私人看板三大引擎的 Python 移植 + DATA 装配器(与私人渲染层同一 schema)。
  chan_analyze()   缠论结构代理(MA/摆动/中枢/枚举分类+模板叙事)   ← backtest/chan_auto.js
  composite()      综合买入评分 Q/T/C/tier/parts/gates            ← backtest/composite.js
  watch_action()   自选操作建议(现价可买/到价再买/回避/可加仓)     ← backtest/daily_review.js
  assemble_payload() 把 diagnose 结果装配成私人 DATA schema(缺数据的模块留空→渲染层自动标灰)
原则与私人版一致: 档位=确定性计算;缺数据给中性分并如实标注,禁止编数。
"""
import time

R = round


def _ma(C, n, i):
    if i + 1 < n:
        return None
    return sum(C[i - n + 1:i + 1]) / n


def _rnd(v):
    if v is None:
        return None
    return round(v) if v >= 100 else (round(v * 2) / 2 if v >= 20 else round(v * 10) / 10)


def chan_analyze(bars):
    """bars: [{date,o,h,l,c},...] 升序 → chan 字段 dict(与 chan_auto.js 同逻辑)。"""
    N = len(bars)
    if N < 25:
        return None
    C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    DT = [str(b.get("date", ""))[:10] for b in bars]
    i = N - 1; last = C[i]
    m5, m10, m20 = _ma(C, 5, i), _ma(C, 10, i), _ma(C, 20, i)
    m60 = _ma(C, 60, i) if N >= 60 else None
    m20p = _ma(C, 20, i - 5) if N >= 25 else None
    m20up = m20p is not None and m20 > m20p * 1.002
    swH, swL = [], []
    for k in range(2, N - 2):
        if H[k] > H[k-1] and H[k] > H[k-2] and H[k] > H[k+1] and H[k] > H[k+2]:
            swH.append((k, H[k]))
        if L[k] < L[k-1] and L[k] < L[k-2] and L[k] < L[k+1] and L[k] < L[k+2]:
            swL.append((k, L[k]))
    h20 = max(H[-20:]); h20i = len(H) - 1 - H[::-1].index(h20)
    h60 = max(H[-60:]) if N >= 60 else max(H)
    l10 = min(L[-10:]); l10i = len(L) - 1 - L[::-1].index(l10)
    l20 = min(L[-20:])
    pullback = (h20 - last) / h20 * 100
    bounce = (last - l10) / l10 * 100
    day_chg = (last - C[i-1]) / C[i-1] * 100 if i >= 1 else 0
    range20 = (h20 - l20) / last * 100
    md = lambda s: s[5:].replace('-', '/') if s else ''
    zg = zd = None
    rH = [x[1] for x in swH if x[0] >= N - 25][-3:]
    rL = [x[1] for x in swL if x[0] >= N - 25][-3:]
    if len(rH) >= 2 and len(rL) >= 2:
        g, d = min(rH), max(rL)
        if g > d:
            zg, zd = g, d

    above = lambda m: m is not None and last > m
    aboveT = lambda m: m is not None and last > m * 0.99
    up_trend = m60 is not None and last > m60 and m20 > m60 and m20up
    reclaimed_short = above(m5) and m10 is not None and last > m10
    reclaimed_all = aboveT(m5) and aboveT(m10) and aboveT(m20) and (m60 is None or aboveT(m60))
    hold_mid = above(m20) and m20up and (m60 is None or last > m60)

    if pullback >= 12:
        if (reclaimed_all or hold_mid) and bounce >= 3:
            cls = 'buy_candidate'
            sig = (f"深回撤后收复全部均线(MA5-{'MA60' if m60 is not None else 'MA20'}),二买候选,守{_rnd(max(l10, m20*0.98))},过{_rnd(h20)}确认"
                   if reclaimed_all else
                   f"回撤守住MA20({_rnd(m20)})上方且MA20仍升,回踩确认候选,守{_rnd(m20*0.98)},过{_rnd(h20)}确认")
        elif (((bounce >= 3 and aboveT(m5)) or bounce >= 6 or day_chg >= 4)) and not (day_chg <= -1 and last < m20 * 0.95):
            cls = 'break_rebound'
            sig = f"超跌反抽:{_rnd(l10)}({md(DT[l10i])})起反弹,收复MA20({_rnd(m20)})前按反抽对待,{_rnd(l10)}不破为前提"
        else:
            cls = 'pending'
            sig = f"下跌未止:站稳{_rnd(l10)}并收复MA10({_rnd(m10)})再看一买,不接飞刀"
    elif up_trend and m20 * 0.97 <= last <= m20 * 1.04:
        cls = 'buy_candidate'
        sig = f"趋势回踩MA20({_rnd(m20)})二买候选,收复MA10({_rnd(m10)})确认,破{_rnd(l10)}失效"
    elif up_trend and (h60 - last) / h60 * 100 <= 6:
        cls = 'buy_candidate'
        sig = f"平台高位近前高{_rnd(h60)},放量突破跟进(三买候选),守{_rnd(max(l10, m20))}"
    elif up_trend and reclaimed_short and bounce >= 3 and pullback >= 4:
        cls = 'buy_candidate'
        sig = f"回踩后收复MA5/10({_rnd(m5)}/{_rnd(m10)}),二买候选,守{_rnd(l10)},过{_rnd(h20)}确认"
    elif up_trend and last > m20 * 1.08:
        cls = 'neutral'
        sig = f"上升趋势但已远离MA20({_rnd(m20)})+{R((last/m20-1)*100)}%,不追,等回踩MA10/20"
    elif up_trend:
        cls = 'neutral'
        sig = f"上升趋势内运行,回踩MA20({_rnd(m20)})或突破{_rnd(h20)}再动"
    elif (not up_trend and not (m20 is not None and abs(last - m20) / m20 <= 0.04 and range20 <= 14)
          and max(pullback, (h60 - last) / h60 * 100) >= 8
          and max(bounce, (last - l20) / l20 * 100) >= 5 and aboveT(m5)):
        cls = 'break_rebound'
        sig = f"弱势反抽:低点反弹中,MA20({_rnd(m20)})/MA60{'('+str(_rnd(m60))+')' if m60 is not None else ''}为压,不破{_rnd(l10)}才有下文"
    elif zg is not None and range20 <= 14:
        cls = 'neutral'
        sig = f"中枢震荡[{_rnd(zd)}-{_rnd(zg)}]:下沿接、上沿减,方向选择后跟进"
    elif m20 is not None and range20 <= 14 and abs(last - m20) / m20 <= 0.05:
        cls = 'neutral'
        sig = f"窄幅震荡贴MA20({_rnd(m20)}):区间{_rnd(l20)}-{_rnd(h20)},突破选向后跟进"
    else:
        cls = 'pending'
        sig = f"结构混沌:等MA5/10/20收敛后选向,参考{_rnd(l10)}支撑/{_rnd(h20)}压力"

    near = lambda a, b: abs(a - b) / b < 0.02
    sup = []
    def push_sup(px, lab):
        if px is not None and px < last * 0.995 and not any(near(s0[0], px) for s0 in sup):
            sup.append((px, lab))
    if m20 is not None and up_trend: push_sup(m20, 'MA20趋势支撑')
    push_sup(l10, md(DT[l10i]) + '低' + str(_rnd(l10)))
    if m60 is not None: push_sup(m60, 'MA60')
    if zd is not None: push_sup(zd, '中枢下沿')
    push_sup(l20, '20日低')
    sup = sorted(sup, key=lambda x: -x[0])[:2]
    res = []
    def push_res(px, lab):
        if px is not None and px > last * 1.005 and not any(near(s0[0], px) for s0 in res):
            res.append((px, lab))
    if m20 is not None and last < m20: push_res(m20, 'MA20反压')
    if zg is not None: push_res(zg, '中枢上沿')
    push_res(h20, md(DT[h20i]) + '高' + str(_rnd(h20)))
    if h60 > h20: push_res(h60, '60日高')
    res = sorted(res, key=lambda x: x[0])[:2]
    buy_zones = [{"px": _rnd(s0[0]), "label": s0[1], "size": '30%' if k == 0 else '40%'} for k, s0 in enumerate(sup)]
    sell_zones = [{"px": _rnd(s0[0]), "label": s0[1], "size": '1/3'} for s0 in res]
    stop = None
    if buy_zones:
        deep = buy_zones[-1]["px"]
        stop = _rnd(min(deep * 0.96, l20 * 0.99))
        if stop >= deep:
            stop = _rnd(deep * 0.95)

    stack = all(a >= b * 0.995 for a, b in zip([m5, m10, m20], [m10, m20, m60]) if a is not None and b is not None)
    stack_txt = '多头排列' if stack and above(m5) else ('价在MA60下' if (m60 is not None and last < m60) else '均线缠绕')
    trend_txt = '上升趋势' if up_trend else ('回撤段' if pullback >= 12 else '震荡')
    state = (f"日线{trend_txt}:MA5({_rnd(m5)})/MA10({_rnd(m10)})/MA20({_rnd(m20)})"
             f"{'/MA60('+str(_rnd(m60))+')' if m60 is not None else ''}{stack_txt};"
             f"20日高{_rnd(h20)}({md(DT[h20i])})回撤{R(pullback)}%,{md(DT[l10i])}低{_rnd(l10)}"
             f"{'获支撑反弹'+str(R(bounce))+'%' if bounce >= 3 else '附近整理'};20日振幅{R(range20)}%")
    return {"chanLevel": "日线", "chanMode": "structure_auto", "chanClass": cls,
            "chanState": state, "chanSignal": sig,
            "buyZones": buy_zones, "sellZones": sell_zones, "stop": stop}


CHAN_Q = {"buy_confirmed": 20, "buy_candidate": 14, "neutral": 10, "pending": 8, "break_rebound": 4, "sell": 0, "none": 8}
CHAN_T = {"buy_confirmed": 25, "buy_candidate": 15, "neutral": 8, "pending": 10, "break_rebound": 5, "sell": 0, "none": 8}
CHAN_TXT = {"buy_confirmed": "买点确认", "buy_candidate": "买点候选待验", "neutral": "中枢震荡",
            "pending": "待信号", "break_rebound": "破位反抽段", "sell": "卖点成立", "none": "无缠论结构"}
ST_T = {"tight": (15, "紧平台·埋伏安全"), "quiet": (12, "低波动安静"), "neutral": (10, "常态"),
        "brk": (3, "破位·不接飞刀"), "hot": (3, "短期过热"), "para": (0, "抛物线")}


def composite(sym, s, stratmap, breakout, holdlv, per_ticker, states, market, today, macro=None):
    """综合买入评分(composite.js 移植;开源版无研报→中性7.5如实标注)。"""
    strat = stratmap.get(sym)
    st = (states.get(sym) or {}).get("st")
    parts, gates = {}, []
    pt = per_ticker.get(sym) or {}
    E = pt.get("expectancy_R")
    if isinstance(E, (int, float)) and pt.get("n"):
        v = 25 if E >= 1 else (15 + (E - 0.5) * 20 if E >= 0.5 else (5 + E * 20 if E >= 0 else 0))
        why = f"{strat or '策略'}期望{E}R({pt.get('n')}笔,胜率{pt.get('win_rate')}%)"
        if pt.get("n", 0) < 5:
            v = min(v, 12.5); why += "·样本过小已压缩"
        parts["backtest"] = {"v": R(v), "max": 25, "why": why}
    else:
        parts["backtest"] = {"v": 12.5, "max": 25, "why": "本票未单独回测(中性)"}
    p8 = s.get("pass")
    parts["sepa"] = ({"v": 15, "max": 30, "why": "新股无SEPA基准(中性)"} if p8 is None
                     else {"v": R(30 * p8 / 8), "max": 30, "why": f"趋势模板{p8}/8"})
    cc = s.get("chanClass") or "none"
    parts["chan"] = {"v": CHAN_Q.get(cc, 8), "max": 20, "why": CHAN_TXT.get(cc, cc)}
    parts["research"] = {"v": 7.5, "max": 15, "why": "无研报覆盖(中性,不惩罚)"}
    stage = s.get("stage") or ""
    from_high = s.get("fromHigh") if s.get("fromHigh") is not None else -99
    if "2" in stage:
        parts["position"] = ({"v": 10, "max": 10, "why": f"Stage2·距高{from_high}%"} if from_high >= -15
                             else {"v": 6, "max": 10, "why": f"Stage2但回撤{from_high}%"} if from_high >= -30
                             else {"v": 3, "max": 10, "why": f"Stage2深回撤{from_high}%"})
    elif "4" in stage or "下跌" in stage:
        parts["position"] = {"v": 0, "max": 10, "why": "下跌阶段"}
    else:
        parts["position"] = {"v": 4, "max": 10, "why": stage or "阶段不明"}
    Q = R(sum(parts[k]["v"] for k in ("backtest", "sepa", "chan", "research", "position")))

    near_trigger = False
    if strat in ("brk", "brk_atr") and breakout.get(sym):
        d2 = breakout[sym][2]
        if d2 <= 0: dv, dwhy, near_trigger = 50, "已过触发价", True
        elif d2 <= 3: dv, dwhy, near_trigger = 35, f"距触发+{d2}%·临界", True
        elif d2 <= 12: dv, dwhy = 15, f"距触发+{d2}%·可挂单等待"
        else: dv, dwhy = 5, f"距触发+{d2}%·筑底中"
    else:
        z1 = None
        if strat == "hold" and holdlv.get(sym):
            z1 = (holdlv[sym].get("buy") or [None])[0]
        elif s.get("buyZones"):
            z1 = s["buyZones"][0]["px"]
        if z1 and s.get("last"):
            d = (s["last"] - z1) / z1 * 100
            if d <= -8: dv, dwhy = 10, f"深破买区{R(d)}%(先看破位门槛)"
            elif d <= 1: dv, dwhy = 50, f"已进买区(距首档{R(d*10)/10}%)"
            elif d <= 6: dv, dwhy = R(50 - 6 * (d - 1)), f"近买区+{R(d*10)/10}%"
            else: dv, dwhy = max(0, R(20 - 2 * (d - 6))), f"距买区+{R(d)}%"
        else:
            dv, dwhy = 5, "无买点定义"
    parts["dist"] = {"v": dv, "max": 50, "why": dwhy}
    parts["trigger"] = {"v": CHAN_T.get(cc, 8), "max": 25, "why": CHAN_TXT.get(cc, cc)}
    stv = ST_T.get(st, (10, "状态未知(中性)"))
    parts["state"] = {"v": stv[0], "max": 15, "why": stv[1]}
    parts["cost"] = {"v": 10, "max": 10, "why": "入场成本正常"}
    T = R(parts["dist"]["v"] + parts["trigger"]["v"] + parts["state"]["v"] + parts["cost"]["v"])
    C = R(0.55 * Q + 0.45 * T)

    hard_avoid = cap_watch = False
    if s.get("stop") and s.get("last") is not None and s["last"] <= s["stop"]:
        gates.append({"id": "G1", "txt": f"⛔破位·信号失效(价{s['last']}≤止损{s['stop']})"}); hard_avoid = True
    if market and not market.get("above"):
        gates.append({"id": "G2", "txt": f"大盘开关红({market.get('gate') or 'SPY'}破200日线)·禁追涨仓位减半"}); cap_watch = True
    if st in ("para", "hot") and near_trigger:
        gates.append({"id": "G3", "txt": "过热状态勿追突破,只等回踩"}); cap_watch = True
    if cc == "sell":
        gates.append({"id": "G5", "txt": "缠论卖点成立"}); cap_watch = True
    # G7 财报前多头拥挤(花旗《人群过滤器》2026-07-10):财报≤7日且拥挤→beat涨少/miss难恢复,压到观察。
    # 开源版拥挤代理只有 IVP/状态灯(无研报台账);财报日来自 earnings 雷达(yfinance)。
    try:
        import datetime as _dt
        t0 = _dt.date.fromisoformat(today)
        ern = next((e for e in (macro or []) if sym in (e.get("ev") or "") and e.get("date")
                    and 0 <= (_dt.date.fromisoformat(e["date"]) - t0).days <= 7), None)
        if ern:
            st_l = (states.get(sym) or {}).get("st")
            why = []
            if s.get("ivp") is not None and s["ivp"] >= 85:
                why.append(f"IVP{s['ivp']}%")
            if st_l in ("hot", "para"):
                why.append("状态" + st_l)
            if why:
                gates.append({"id": "G7", "txt": f"财报前拥挤({ern['date'][5:]}财报·{'/'.join(why)}):beat涨少/miss难恢复,财报前禁加仓"})
                cap_watch = True
    except Exception:
        pass

    if hard_avoid:
        tier, tier_txt = "avoid", "回避·破位失效"
    else:
        tier = "buy" if (C >= 70 and Q >= 60 and T >= 55) else ("watch" if C >= 45 else "avoid")
        if tier == "buy" and cap_watch:
            g0 = next((g for g in gates if g["id"] != "G6"), None)
            tier, tier_txt = "watch", "观察·" + (g0["txt"][:12] if g0 else "受限")
        elif tier == "watch" and Q >= 70 and T < 40:
            tier_txt = "观察·好票等回踩"
        elif tier == "watch" and T >= 70 and Q < 45:
            tier_txt = "观察·到价勿接(结构弱)"
        else:
            tier_txt = {"buy": "买入", "watch": "观察", "avoid": "回避"}[tier]
    return {"Q": Q, "T": T, "C": C, "tier": tier, "tierTxt": tier_txt, "gates": gates, "parts": parts, "asOf": today}


def watch_action(sym, s, held):
    """自选操作建议(daily_review.js watchActionFor 移植)。→ {cls,tag,text}"""
    tier = (s.get("compo") or {}).get("tier") or s.get("verdict")
    last = s.get("last")
    B = (s.get("buyZones") or [None])[0]
    S = (s.get("sellZones") or [None])[0]
    stop = s.get("stop")
    bs = None
    if B and last is not None:
        px = B["px"]
        if px * 0.985 <= last <= px * 1.015:
            bs = {"at": True, "breakout": px >= last, "word": "现价即买点", "px": px}
        elif px > last:
            bs = {"at": False, "breakout": True, "word": "突破", "px": px, "near": last >= px * 0.98}
        else:
            bs = {"at": False, "breakout": False, "word": "回踩", "px": px, "near": last <= px * 1.02}
    at_sell = S and last is not None and last >= S["px"]
    g = f",止损${stop}" if stop else ""
    if held:
        if bs and (bs["at"] or (not bs["breakout"] and bs.get("near"))):
            return {"cls": "buy", "tag": "可加仓", "text": f"现价${last}回到买区${B['px']},持仓可加{B.get('size','')}{g}"}
        if at_sell:
            return {"cls": "trim", "tag": "可减仓", "text": f"现价${last}触止盈${S['px']},减{S.get('size','部分')}锁利"}
        return {"cls": "hold", "tag": "持有", "text": f"{'回踩$'+str(B['px'])+'可加' if B else '守支撑'}、{'涨$'+str(S['px'])+'减' if S else '压力位减'}"}
    if tier == "buy":
        if bs and bs["at"]:
            return {"cls": "buy", "tag": "现价可买", "text": f"现价${last}已在买区${B['px']},可分批建仓{g}"}
        if bs:
            return {"cls": "dip", "tag": f"{bs['word']}可买", "text": f"{bs['word']}${bs['px']}可买入,现价${last}{g}"}
        return {"cls": "buy", "tag": "可买入", "text": f"现价${last}分批建仓{g or ',止损前低'}"}
    if tier == "watch":
        if bs:
            return {"cls": "watch", "tag": "观望·到价再买", "text": f"{bs['word']}${bs['px']}{'放量确认' if bs['breakout'] else '企稳'}再进,现价${last}"}
        return {"cls": "watch", "tag": "观望", "text": "结构未明,等信号确认再动"}
    if bs and not bs["breakout"]:
        return {"cls": "avoid", "tag": "回避", "text": f"不追;跌到${B['px']}且结构转稳才有价值"}
    return {"cls": "avoid", "tag": "回避", "text": "结构未稳,暂不参与"}


def pos_action(p):
    """持仓操作建议(正股版;daily_review.js actionFor/planFor 移植,开源 v1 仅支持 STK)。"""
    up = p.get("uPnl") or 0
    last, stop = p.get("last"), p.get("stop")
    B = (p.get("buyZones") or [None])[0]
    S = (p.get("sellZones") or [None])[0]
    plan_parts = []
    if S: plan_parts.append(f"止盈区${S['px']}")
    if B: plan_parts.append(f"回踩${B['px']}加")
    if stop: plan_parts.append(f"止损${stop}")
    plan = " · ".join(plan_parts)
    if stop and last is not None and last <= stop:
        return {"cls": "danger", "tag": "止损", "text": f"跌破止损${stop},离场保护本金,不扛。", "plan": plan}
    if S and last is not None and last >= S["px"]:
        return {"cls": "warn", "tag": "减仓锁利", "text": f"触减仓区${S['px']},减{S.get('size','部分')}锁利。", "plan": plan}
    if B and last is not None and last <= B["px"] * 1.02:
        return {"cls": "do", "tag": "可加仓", "text": f"回踩入场区${B['px']},激进可加{B.get('size','')},止损${stop or '前低'}。", "plan": plan}
    if up > 0:
        return {"cls": "hold", "tag": "持有", "text": f"浮盈${R(up)},{'触$'+str(S['px'])+'分批止盈' if S else '移动止损跟涨'}。", "plan": plan}
    return {"cls": "wait", "tag": "持有观察", "text": f"{'触$'+str(S['px'])+'减、回$'+str(B['px'])+'加' if (S and B) else '随结构进出'}。", "plan": plan}


def assemble_payload(results, cfg, extras, barsmap):
    """把 diagnose 结果 + extras 装配成私人 DATA schema;缺的模块留空(渲染层标灰)。"""
    today = time.strftime("%Y-%m-%d")
    now = time.strftime("%Y-%m-%d %H:%M")
    source = cfg.get("source", "yahoo")
    extras = extras or {}
    stratmap, breakout, holdlv, per_ticker, states, signals = {}, {}, {}, {}, {}, {}

    for rec in results:
        sym = rec["ticker"]
        strat = rec.get("strategy")
        if strat:
            stratmap[sym] = strat
        sg = rec.get("signal") or {}
        if sg.get("type") == "breakout" and sg.get("trigger"):
            breakout[sym] = [sg["trigger"], sg.get("stop"), sg.get("to_pivot", 99)]
        if strat == "hold" and sg.get("buy_zones") and rec.get("hold_stats"):
            hs = rec["hold_stats"]
            holdlv[sym] = {"buy": sg["buy_zones"], "target": sg.get("targets") or [], "stop": sg.get("stop"),
                           "bh": hs.get("buy_hold_pct"), "cagr": hs.get("cagr"), "dd": hs.get("max_dd")}
        bt = rec.get("backtest") or {}
        if strat in bt:
            per_ticker[sym] = bt[strat]
        if rec.get("state"):
            states[sym] = rec["state"]
        chan = chan_analyze(barsmap.get(sym) or []) or {}
        s = {"name": rec.get("name") or sym, "last": rec.get("last"), "chg": rec.get("chg"),
             "stage": rec.get("stage"), "pass": rec.get("tt_pass"), "fromHigh": rec.get("pct_from_high"),
             "note": rec.get("action") or ""}
        s.update(chan)
        # —— A股增强(ashare 分支):原生缠论(笔/中枢/背驰)覆盖结构判断;价位仍用结构引擎买卖区 ——
        ash = rec.get("ashare") or {}
        ch = ash.get("chan") or {}
        if ch.get("mode") == "chan":
            CLS_MAP = {"buy1": "buy_candidate", "buy3": "buy_candidate", "neutral": "neutral",
                       "break": "pending", "sell": "sell"}
            s["chanMode"] = "chanlun_native"
            s["chanState"] = ch.get("state") or s.get("chanState")
            if ch.get("signal"):
                s["chanSignal"] = ch["signal"]
            if ch.get("cls") in CLS_MAP:
                s["chanClass"] = CLS_MAP[ch["cls"]]
        if ash:
            bits = []
            bd = ash.get("board") or {}
            if bd.get("board"):
                bits.append(f"{bd['board']}{'±' + str(bd.get('limit_pct')) + '%' if bd.get('limit_pct') else ''}" + ("·ST⚠️" if bd.get("st") else ""))
            lm = ash.get("limit") or {}
            if lm.get("state") and lm["state"] not in ("normal", "无"):
                bits.append(f"今日{lm['state']}")
            tv = ash.get("turnover") or {}
            if tv.get("turnover_now_pct") is not None:
                bits.append(f"换手{tv['turnover_now_pct']}%(分位{tv.get('turnover_percentile', '—')})")
            db = ash.get("daban") or {}
            if db.get("mode") and db.get("n"):
                bits.append(f"打板样本{db['n']}·续板率{db.get('续板率%', '—')}%·次日最差{db.get('次日最差%', '—')}%")
            if bits:
                s["note"] = "【A股】" + " · ".join(bits) + ("。" + s["note"] if s["note"] else "")
        signals[sym] = s

    market = extras.get("market")
    # 财报日历(提前构建,G7财报前拥挤闸门要用;payload 复用同一变量)
    macro = [{"date": e.get("date"), "ev": f"{e.get('t') or e.get('ticker')} 财报", "impact": "高"}
             for e in (extras.get("earnings") or []) if e.get("date")]
    for sym, s in signals.items():
        s["compo"] = composite(sym, s, stratmap, breakout, holdlv, per_ticker, states, market, today, macro=macro)
        s["verdict"] = s["compo"]["tier"]

    # 持仓(config.json 可选 "positions":[{"sym","qty","avgCost"}] 正股)
    positions = []
    for p0 in cfg.get("positions", []):
        sym = p0.get("sym")
        s = signals.get(sym) or {}
        last = s.get("last")
        qty, avg = p0.get("qty", 0), p0.get("avgCost", 0)
        p = {"sym": sym, "type": "STK", "qty": qty, "avgCost": avg, "last": last,
             "chgPct": s.get("chg"), "name": s.get("name") or sym, "sector": "",
             "mktVal": R(qty * last, 2) if last else None,
             "uPnl": R(qty * (last - avg), 2) if last else None,
             "chanLevel": s.get("chanLevel"), "chanMode": s.get("chanMode"), "chanState": s.get("chanState"),
             "chanSignal": s.get("chanSignal"), "buyZones": s.get("buyZones"), "sellZones": s.get("sellZones"),
             "stop": s.get("stop"), "verdict": "hold", "verdictTxt": "持有", "note": p0.get("note", "")}
        p["action"] = pos_action(p)
        positions.append(p)
    held = {p["sym"] for p in positions}

    wsum = {"buy": 0, "dip": 0, "watch": 0, "avoid": 0, "add": 0, "hold": 0, "trim": 0}
    for sym, s in signals.items():
        w = watch_action(sym, s, sym in held)
        s["wact"] = w
        key = ("add" if w["tag"] == "可加仓" else "trim" if w["tag"] == "可减仓" else
               w["cls"] if w["cls"] in wsum else None)
        if key:
            wsum[key] += 1

    daily = None
    if positions:
        n_up = sum(1 for p in positions if (p.get("chgPct") or 0) > 0)
        n_dn = sum(1 for p in positions if (p.get("chgPct") or 0) < 0)
        tot = R(sum(p.get("uPnl") or 0 for p in positions))
        rank = {"danger": 0, "warn": 1, "do": 2}
        todo = [{"sym": p["sym"], "label": "正股", "cls": p["action"]["cls"], "tag": p["action"]["tag"],
                 "text": p["action"]["text"], "plan": p["action"].get("plan")}
                for p in sorted([p for p in positions if p["action"]["cls"] in rank],
                                key=lambda p: rank[p["action"]["cls"]])]
        tone = "持仓多数承压" if n_dn > n_up * 1.5 else ("持仓普遍走强" if n_up > n_dn * 1.5 else "涨跌互现")
        daily = {"asOf": now, "brief": f"{tone}({n_up}涨{n_dn}跌,合计{'+' if tot>=0 else ''}${tot})。",
                 "counts": {"urgent": sum(1 for p in positions if p['action']['cls'] == 'danger'),
                            "trim": sum(1 for p in positions if p['action']['cls'] == 'warn'),
                            "add": sum(1 for p in positions if p['action']['cls'] == 'do'),
                            "hold": sum(1 for p in positions if p['action']['cls'] in ('hold', 'wait'))},
                 "todo": todo,
                 "note": "决策辅助,非投资建议。建议由持仓数据规则化生成,点位为结构参考。"}

    # 今日决策卡(结论先行首页):持仓待办+自选可动手合并 + 买入档清单 + 通过门槛期权 + 盯价
    todo_syms = {t["sym"] for t in (daily or {}).get("todo", [])}
    acts = [dict(t, src="持仓") for t in (daily or {}).get("todo", [])]
    watch_px, buy_list = [], []
    for sym, s in signals.items():
        w = s.get("wact") or {}
        if (w.get("cls") == "buy" or w.get("tag") == "可减仓") and sym not in todo_syms:
            acts.append({"src": "自选", "sym": sym, "label": "", "cls": "do" if w.get("cls") == "buy" else "warn",
                         "tag": w.get("tag"), "text": w.get("text"), "plan": f"止损${s['stop']}" if s.get("stop") else ""})
        elif w.get("cls") == "dip" and s.get("buyZones"):
            watch_px.append({"sym": sym, "word": "破" if "突破" in (w.get("tag") or "") else "回", "px": s["buyZones"][0]["px"]})
        if (s.get("compo") or {}).get("tier") == "buy":
            buy_list.append({"sym": sym, "C": s["compo"]["C"], "held": sym in held,
                             "tag": w.get("tag", ""), "text": w.get("text", ""), "stop": s.get("stop")})
    buy_list.sort(key=lambda x: -x["C"])
    rank2 = {"danger": 0, "warn": 1, "do": 2}
    acts.sort(key=lambda a: rank2.get(a.get("cls"), 3))
    opt_picks = [{"t": r.get("t"), "expiry": r.get("expiry"), "dte": r.get("dte"), "K": r.get("K") or r.get("strike"),
                  "mid": r.get("mid"), "ev": r.get("ev") or r.get("EV"), "pw": r.get("pw") or r.get("P_win"), "gates": "✅"}
                 for r in (extras.get("top10") or []) if not r.get("gates")][:5]
    n_up_w = sum(1 for s in signals.values() if (s.get("chg") or 0) > 0)
    n_dn_w = sum(1 for s in signals.values() if (s.get("chg") or 0) < 0)
    decision = {
        "asOf": now,
        "brief": (daily or {}).get("brief") or f"自选池{n_up_w}涨{n_dn_w}跌;无持仓数据,行动清单为自选买卖点。",
        "counts": {"urgent": sum(1 for a in acts if a["cls"] == "danger"),
                   "trim": sum(1 for a in acts if a["cls"] == "warn"),
                   "act": sum(1 for a in acts if a["cls"] == "do"),
                   "px": len(watch_px), "buy": len(buy_list), "opt": len(opt_picks)},
        "acts": acts, "watchPx": watch_px, "buyList": buy_list, "optPicks": opt_picks,
        "optAsOf": now if opt_picks else "",
        "note": "决策辅助,非投资建议。行动清单=持仓处置+自选买卖点合并去重;点位为结构参考。",
    }

    alerts = []
    if market:
        gate = market.get("gate") or "SPY"
        alerts.append(["green" if market.get("above") else "red",
                       f"大盘开关:{gate} {market.get('spy')} {'在200日线上方(+'+str(market.get('pct'))+'%),允许正常仓位' if market.get('above') else '跌破200日线('+str(market.get('pct'))+'%),禁追涨·仓位减半(Faber)'}"
                       + (("<br>" + market["ashare_note"]) if market.get("ashare_note") else "")])
    if extras.get("clusters"):
        alerts.append(["blue", "<b>相关簇限仓</b>:高相关票≈同一注,每簇最多1-2个仓位:" +
                       " · ".join("[" + " ".join(c) + "]" for c in extras["clusters"][:4])])

    groups = cfg.get("groups") or [{"name": "自选 Watchlist", "tickers": [r["ticker"] for r in results]}]
    payload = {
        "title": cfg.get("title", "Stock Strategy Dashboard"),
        "asOf": now + f"(数据源 {source})", "deepAsOf": today + " 结构自动",
        "marketOpen": None, "source": source,
        "capital": cfg.get("capital", 10000), "riskPct": cfg.get("risk_pct", 1.5),
        "account": cfg.get("account") or {}, "positions": positions,
        "heldSyms": sorted(held), "soldSyms": [], "verifySyms": [],
        "sectors": groups, "signals": signals,
        "backtest": {"optimized": {"stratmap": stratmap, "breakout": breakout, "holdlv": holdlv},
                     "per_ticker": per_ticker},
        "states": states, "market": market, "corr": extras.get("clusters") or [],
        "gapstats": None, "macroCal": macro,
        "movers": extras.get("movers"), "dark": extras.get("dark"),
        "darkprints": None, "extended": None,
        "options": ({"scan": extras.get("top10") or [], "scanAsOf": now} if extras.get("top10") else {}),
        "intel": [], "research": [], "researchMeta": None, "audit": extras.get("audit"),
        "portRisk": None, "dailyReview": daily, "decision": decision, "watchSummary": dict(asOf=now, **wsum),
        "alerts": alerts,
        "meta": {"firstRun": not results, "source": source, "engine": "opensource"},
    }
    return payload
