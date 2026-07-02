"""
Per-ticker diagnosis: classify each stock and assign the strategy that historically
fits it — dip-buy, breakout, or avoid — then produce current actionable levels.
This is the "diagnose every ticker, use a different strategy per type" core.
"""
from .indicators import sma, annualized_vol, atr
from .backtest import dip_trades, brk_trades, brk_atr_trades, agg


def _stage(C, n):
    s50 = sma(C, 50, n - 1); s150 = sma(C, 150, n - 1); s200 = sma(C, 200, n - 1)
    s2p = sma(C, 200, n - 21) if n >= 221 else None
    if None in (s50, s150, s200):
        return "数据不足", s50, s200
    up = C[-1] > s200 and s50 > s150 and (s2p is None or s200 > s2p)
    dn = C[-1] < s200 and s50 < s150
    return ("Stage2上升" if up else "Stage4下跌" if dn else "过渡/震荡"), s50, s200


def diagnose(ticker, bars, name=None):
    n = len(bars)
    C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    last = C[-1]
    chg = round((C[-1] / C[-2] - 1) * 100, 2) if n >= 2 else 0
    stage, s50, s200 = _stage(C, n)
    vol = round(annualized_vol(C), 0)
    hi252 = max(H[-252:]) if n >= 252 else max(H)
    pct_from_high = round((last - hi252) / hi252 * 100, 1)

    rec = {"ticker": ticker, "name": name or ticker, "last": round(last, 2), "chg": chg,
           "stage": stage, "vol": vol, "pct_from_high": pct_from_high, "bars": n}

    if n < 250:
        rec.update({"strategy": "avoid", "bucket": "历史不足·新标的",
                    "action": f"日线仅 {n} 根,样本不足,先观察积累,勿套回测结论。",
                    "backtest": {}})
        return rec

    d = agg(dip_trades(bars)); dr = agg(dip_trades(bars, True))
    bk = agg(brk_trades(bars)); ba = agg(brk_atr_trades(bars))
    rec["backtest"] = {"dip": d, "dip_re": dr, "brk": bk, "brk_atr": ba}

    # pick the strategy with the highest positive expectancy & enough signals
    best, bexp = "avoid", 0.10
    for key, res in (("dip", d), ("dip_re", dr), ("brk", bk), ("brk_atr", ba)):
        if res["n"] >= 5 and res["expectancy_R"] > bexp:
            best, bexp = key, res["expectancy_R"]
    rec["strategy"] = best

    if best == "avoid":
        if pct_from_high <= -45:
            rec["bucket"] = "抛物线后崩塌/破位"
            rec["action"] = f"从高点腰斩({pct_from_high}%),接飞刀区。等站回200日线+构筑≥6周缩量平台再看,当前不碰。"
        elif stage == "Stage4下跌":
            rec["bucket"] = "下跌弱势·非Stage2"
            rec["action"] = "价在200日线下、均线空头。趋势没转多前不碰,等收复200日线走出Stage2基底。"
        elif vol >= 70:
            rec["bucket"] = "高波动·易被洗"
            rec["action"] = f"趋势在但年化波动{int(vol)}%,机械止损反复被扫。等波动收缩成紧致基底(VCP)再当突破打;否则止损放宽2倍+仓位减半,或跳过。"
        else:
            rec["bucket"] = "震荡无趋势"
            rec["action"] = "均线纠缠来回洗。只在区间极值小仓博弹或跳过,等趋势明朗。"
        rec["signal"] = {}
        return rec

    # actionable current levels for the assigned strategy
    if best in ("brk", "brk_atr"):
        pivot = round(max(H[-31:-1]), 2) if n >= 31 else round(max(H), 2)
        to_piv = round((pivot - last) / last * 100, 1)
        status = ("临界突破·可挂单" if to_piv <= 12 else f"筑底中·距触发+{to_piv}%")
        if best == "brk_atr":
            a = atr(H, L, C, n - 1); stop = round(pivot - 2.0 * a, 2)
            rec["signal"] = {"type": "breakout", "trigger": pivot, "stop": stop, "to_pivot": to_piv, "status": status, "wide": True}
            rec["action"] = f"高波动·宜突破+宽止损:突破 > ${pivot} 买入({status}),ATR宽止损 ${stop}(约2×ATR),仓位减半。别抄底、别用紧止损。"
        else:
            stop = round(min(L[-10:]) * 0.98, 2)
            rec["signal"] = {"type": "breakout", "trigger": pivot, "stop": stop, "to_pivot": to_piv, "status": status}
            rec["action"] = f"该票宜追涨:突破 > ${pivot} 买入({status}),止损 ${stop}。别回踩抄底。"
    else:
        # dip buy zones anchored near SMA50 / recent structure
        z1 = round(s50 * 1.005, 2); z2 = round(s50 * 0.97, 2); z3 = round(min(L[-20:]) * 0.99, 2)
        stop = round(min(L[-5:]) * 0.98, 2)
        rec["signal"] = {"type": "dip", "buy_zones": [z1, z2, z3], "stop": stop,
                         "note": "回踩50MA企稳分批;半仓+2R锁胜、半仓跟50MA跑。" + ("止损后收复入场价可再进场。" if best == "dip_re" else "")}
        rec["action"] = f"该票宜抄底:回踩 ${z1}/${z2}/${z3} 分批买,止损 ${stop}。"
    return rec
