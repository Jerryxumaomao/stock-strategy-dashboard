"""
打板 (limit-up board chasing) — A-share retail's most active AND most dangerous style.
首板/连板 识别 + 封板质量(一字/炸板/放量) + 打板胜率回测(买涨停收盘、T+1次日出)。

⚠️ 诚实前提(务必读,也写进看板):
  * 打板是**负期望游戏对大多数散户**——次日"高开低走"割肉是常态;只有有速度/信息优势的
    游资长期能赢。本模块用回测把这个真相量化,不是教你打板,是让你看清风险。
  * 日线数据只能近似:拿不到 封单量/封板时间/分时炸板 —— 那些需要 L2/tick 数据。故本模块的
    "封板质量"是日线代理(一字=一字板不可追;收盘在板=尾盘可打;摸板未封=炸板)。
  * 打板只在**情绪发酵/高潮期**有效,退潮期是绞肉机;务必配合 run.py review-cn 的情绪周期看。
决策辅助,非投资建议。
"""


def _pc(bars, i):
    return bars[i - 1]["c"]


def annotate(bars, lim=0.10):
    """逐日标注涨停结构。返回每根 bar 的 dict: limit_up/sealed(一字)/zhaban(炸板)/streak(连板数)/vol_ratio。"""
    n = len(bars); out = [None] * n
    for i in range(1, n):
        pc = _pc(bars, i)
        if pc <= 0:
            out[i] = {"limit_up": False}; continue
        lu = pc * (1 + lim); eps = pc * 0.004
        c, h, l = bars[i]["c"], bars[i]["h"], bars[i]["l"]
        limit_up = c >= lu - eps
        sealed = limit_up and l >= lu - eps            # 一字/T字板:全天在板,追不进
        touched = h >= lu - eps                          # 盘中摸到涨停
        zhaban = touched and not limit_up                # 炸板:摸板未能收在板上(弱)
        v = bars[i].get("v", 0)
        avgv = sum(bars[j].get("v", 0) for j in range(max(0, i - 20), i)) / max(1, min(20, i))
        out[i] = {"limit_up": limit_up, "sealed": sealed, "zhaban": zhaban,
                  "vol_ratio": round(v / avgv, 2) if avgv else None}
    # 连板数(含当日,连续收在涨停)
    streak = 0
    for i in range(1, n):
        streak = streak + 1 if out[i] and out[i]["limit_up"] else 0
        if out[i]:
            out[i]["streak"] = streak
            out[i]["first_board"] = (out[i]["limit_up"] and streak == 1)
    return out


def daban_backtest(bars, lim=0.10, mode="first"):
    """打板回测: 在涨停日买入(收盘价≈涨停价,模拟尾盘打板),T+1 次日卖出。
    mode='first' 只打首板; 'continuation' 只打已连板(接力); 'all' 全打。
    跳过一字板(追不进)。度量: 次日开盘/收盘收益、胜率、续板率、炸板(次日转跌)率。"""
    n = len(bars); ev = annotate(bars, lim)
    trades = []
    for i in range(1, n - 1):
        e = ev[i]
        if not e or not e["limit_up"] or e["sealed"]:   # 非涨停 或 一字板追不进 -> 跳过
            continue
        if mode == "first" and not e["first_board"]:
            continue
        if mode == "continuation" and e["streak"] < 2:
            continue
        entry = bars[i]["c"]                            # 尾盘打板≈涨停价
        no, nc = bars[i + 1]["o"], bars[i + 1]["c"]     # 次日开/收(T+1才能卖)
        r_open = (no / entry - 1) * 100                 # 次日开盘就卖
        r_close = (nc / entry - 1) * 100                # 持到次日收盘
        cont = ev[i + 1] and ev[i + 1]["limit_up"]      # 次日续板(又涨停)
        trades.append({"r_open": r_open, "r_close": r_close, "cont": bool(cont),
                       "streak": e["streak"], "vol_ratio": e.get("vol_ratio")})
    if not trades:
        return {"n": 0, "mode": mode}
    import statistics as st
    ro = [t["r_open"] for t in trades]; rc = [t["r_close"] for t in trades]
    return {
        "mode": mode, "n": len(trades), "小样本存疑": len(trades) < 10,
        "次日开盘卖_均值%": round(st.mean(ro), 2), "次日开盘卖_胜率%": round(sum(1 for x in ro if x > 0) / len(ro) * 100, 1),
        "次日收盘卖_均值%": round(st.mean(rc), 2), "次日收盘卖_胜率%": round(sum(1 for x in rc if x > 0) / len(rc) * 100, 1),
        "续板率%": round(sum(1 for t in trades if t["cont"]) / len(trades) * 100, 1),
        # 尾部风险(打板真正杀人的地方,不是均值)
        "次日最差%": round(min(rc), 1), "次日跌超5%占比%": round(sum(1 for x in rc if x < -5) / len(rc) * 100, 1),
        "警示": "⚠️此均值高估真实打板收益: ①强封板(封死)你买不进,能成交的是弱板=幸存者偏差 "
              "②全周期混合,退潮期会剧烈反转为负 ③未含滑点/佣金/情绪割肉。看'次日最差%'和'跌超5%占比'"
              "才是打板的真面目——散户多亏正是死在这条尾巴上。仅供认识风险,非鼓励打板。",
    }


def daban_scan(bars, lim=0.10, name=""):
    """最新一日的打板状态: 首板/N连板/炸板/无 + 封板质量(一字?放量?) + 诚实信号。"""
    if not bars or len(bars) < 22:
        return {"state": "数据不足"}
    ev = annotate(bars, lim)
    e = ev[-1]
    if not e or not e["limit_up"]:
        if e and e["zhaban"]:
            return {"state": "炸板", "signal": "⚠️今日摸涨停未封=炸板,资金分歧/接力失败,弱势,勿追", "cls": "sell"}
        # 昨日是否涨停(今日回落)
        y = ev[-2]
        if y and y["limit_up"]:
            return {"state": "断板", "signal": "昨涨停今未续=断板,连板终结,注意退潮", "cls": "neutral"}
        return {"state": "无", "signal": None, "cls": "neutral"}
    streak = e["streak"]
    q = []
    if e["sealed"]:
        q.append("一字板(追不进,勿挂高价)")
    if e.get("vol_ratio") and e["vol_ratio"] >= 2:
        q.append("放量" + str(e["vol_ratio"]) + "倍")
    elif e.get("vol_ratio") and e["vol_ratio"] <= 0.7:
        q.append("缩量(封板存疑)")
    label = ("首板" if streak == 1 else str(streak) + "连板")
    sig = "🔥%s%s。打板高风险:次日高开低走割肉是常态,仅情绪发酵期+龙头才考虑,务必看情绪周期(review-cn)。" % (
        label, ("·" + "·".join(q) if q else ""))
    return {"state": label, "streak": streak, "sealed": e["sealed"],
            "vol_ratio": e.get("vol_ratio"), "signal": sig,
            "cls": "buy" if (streak >= 1 and not e["sealed"]) else "neutral"}
