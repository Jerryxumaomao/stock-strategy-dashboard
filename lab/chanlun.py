"""
缠论 (Chan Theory / 缠中说禅) — self-contained engine on daily OHLC bars.
Chanlun is A-share NATIVE (缠中说禅 traded A-shares), so the ashare branch treats it as
a first-class signal. Works on any [{o,h,l,c}] series (A股/港股/ETF/指数/期货).

Pipeline (faithful but pragmatic, daily level):
  1. 包含关系处理 (inclusion merge)  -> 去掉K线包含,保留方向
  2. 分型 (fractals)                  -> 顶分型/底分型
  3. 笔 (strokes)                     -> 顶↔底交替连接,间隔>=1根(经典>=5根含端点)
  4. 中枢 (pivots)                    -> 连续3笔重叠区间 [ZD, ZG]
  5. 背驰 (divergence)                -> MACD 红/绿柱面积对比(同向两段)
  6. 买卖点 (1/2/3 buy&sell)          -> 一买=下跌背驰; 二买=回抽不破前低; 三买=中枢突破回踩不回中枢

Returns a compact dict the dashboard renders (state / signal / pivot / divergence / levels).
Not investment advice. Rule-based proxy of chanlun; honest about its limits on small samples.
"""


def _ema(vals, n):
    k = 2 / (n + 1)
    out = []
    e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _macd(closes, fast=12, slow=26, sig=9):
    if len(closes) < slow + sig:
        return [0] * len(closes)
    ef, es = _ema(closes, fast), _ema(closes, slow)
    dif = [a - b for a, b in zip(ef, es)]
    dea = _ema(dif, sig)
    return [d - s for d, s in zip(dif, dea)]  # MACD 柱 (bar)


def _merge_inclusion(bars):
    """处理包含关系:后一根被前一根包含(或反包)时,按当前方向合并成一根。"""
    if not bars:
        return []
    ks = [dict(h=bars[0]["h"], l=bars[0]["l"], i=0)]
    direction = 1
    for idx in range(1, len(bars)):
        h, l = bars[idx]["h"], bars[idx]["l"]
        top = ks[-1]
        contained = (h <= top["h"] and l >= top["l"]) or (h >= top["h"] and l <= top["l"])
        if contained:
            if direction > 0:  # 向上取高高
                top["h"] = max(top["h"], h); top["l"] = max(top["l"], l)
            else:              # 向下取低低
                top["h"] = min(top["h"], h); top["l"] = min(top["l"], l)
            top["i"] = idx
        else:
            direction = 1 if h > top["h"] else -1
            ks.append(dict(h=h, l=l, i=idx))
    return ks


def _fractals(ks):
    """分型:三根合并K线,中间最高=顶分型,中间最低=底分型。"""
    fr = []
    for j in range(1, len(ks) - 1):
        a, b, c = ks[j - 1], ks[j], ks[j + 1]
        if b["h"] > a["h"] and b["h"] > c["h"]:
            fr.append(dict(kind="top", px=b["h"], i=b["i"], j=j))
        elif b["l"] < a["l"] and b["l"] < c["l"]:
            fr.append(dict(kind="bot", px=b["l"], i=b["i"], j=j))
    return fr


def _strokes(fr, min_gap=4):
    """笔:顶↔底交替;同类型取更极端者;间隔(合并K数)>=min_gap 才成笔。"""
    if not fr:
        return []
    seq = [fr[0]]
    for f in fr[1:]:
        last = seq[-1]
        if f["kind"] == last["kind"]:
            if (f["kind"] == "top" and f["px"] >= last["px"]) or (f["kind"] == "bot" and f["px"] <= last["px"]):
                seq[-1] = f  # 同类型取更极端
        else:
            if abs(f["j"] - last["j"]) >= min_gap:
                seq.append(f)
    strokes = []
    for a, b in zip(seq, seq[1:]):
        strokes.append(dict(dir="up" if b["kind"] == "top" else "down",
                            i0=a["i"], i1=b["i"], p0=a["px"], p1=b["px"]))
    return strokes


def _pivots(strokes):
    """中枢:连续3笔的重叠区间 [ZD, ZG]。返回最后一个中枢。"""
    piv = None
    for k in range(len(strokes) - 2):
        s1, s2, s3 = strokes[k], strokes[k + 1], strokes[k + 2]
        hi = min(max(s1["p0"], s1["p1"]), max(s3["p0"], s3["p1"]))
        lo = max(min(s1["p0"], s1["p1"]), min(s3["p0"], s3["p1"]))
        if hi > lo:  # 有重叠
            piv = dict(zg=round(hi, 2), zd=round(lo, 2), end=s3["i1"])
    return piv


def analyze(bars, name=""):
    """主入口。返回缠论结构摘要(供看板渲染)。数据不足则诚实降级。"""
    if not bars or len(bars) < 40:
        return {"mode": "insufficient", "state": "数据不足(<40根),缠论降级", "signal": None}
    closes = [b["c"] for b in bars]
    macd = _macd(closes)
    ks = _merge_inclusion(bars)
    fr = _fractals(ks)
    strokes = _strokes(fr)
    if len(strokes) < 3:
        return {"mode": "proxy", "state": "笔不足(结构未成型)", "signal": None,
                "strokes": len(strokes)}
    piv = _pivots(strokes)
    last = strokes[-1]
    price = closes[-1]

    # 背驰:最后一段下跌(或上涨)与前一同向段比 MACD 面积
    def seg_area(s):
        return sum(abs(m) for m in macd[s["i0"]:s["i1"] + 1] if (m < 0) == (s["dir"] == "down"))
    div = None
    same_dir = [s for s in strokes if s["dir"] == last["dir"]]
    if len(same_dir) >= 2:
        a_now, a_prev = seg_area(same_dir[-1]), seg_area(same_dir[-2])
        made_extreme = (last["dir"] == "down" and last["p1"] <= same_dir[-2]["p1"]) or \
                       (last["dir"] == "up" and last["p1"] >= same_dir[-2]["p1"])
        if made_extreme and a_prev > 0 and a_now < a_prev * 0.9:
            div = ("底背驰" if last["dir"] == "down" else "顶背驰")

    # 买卖点分类
    signal, cls = None, "neutral"
    if piv:
        if price > piv["zg"] and last["dir"] == "up":
            signal, cls = "三买候选:中枢突破,回踩不破ZG(%.2f)确认" % piv["zg"], "buy3"
        elif piv["zd"] <= price <= piv["zg"]:
            signal, cls = "中枢内震荡(ZD %.2f~ZG %.2f):等突破或背驰" % (piv["zd"], piv["zg"]), "neutral"
        elif price < piv["zd"]:
            if div == "底背驰":
                signal, cls = "一买候选:跌破中枢且底背驰(动能衰竭)", "buy1"
            else:
                signal, cls = "破位下行(<ZD %.2f):无背驰前不接" % piv["zd"], "break"
    if div == "底背驰" and cls not in ("buy1",):
        signal, cls = (signal + " · 底背驰迹象" if signal else "底背驰迹象:关注二买"), ("buy2" if cls == "neutral" else cls)
    if div == "顶背驰":
        signal = (signal + " · ⚠️顶背驰(减仓信号)" if signal else "⚠️顶背驰:同级卖点,减仓")
        cls = "sell"

    return {
        "mode": "chan", "cls": cls,
        "state": ("上升笔" if last["dir"] == "up" else "下降笔") +
                 (" · 中枢 ZD %.2f~ZG %.2f" % (piv["zd"], piv["zg"]) if piv else " · 无中枢") +
                 (" · " + div if div else ""),
        "signal": signal,
        "pivot": piv, "divergence": div, "n_strokes": len(strokes),
        "last_dir": last["dir"],
    }
