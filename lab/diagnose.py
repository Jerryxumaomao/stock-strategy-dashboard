"""
Per-ticker diagnosis: classify each stock and assign the strategy that historically
fits it — dip-buy, breakout, or avoid — then produce current actionable levels.
This is the "diagnose every ticker, use a different strategy per type" core.
"""
from .indicators import sma, annualized_vol, atr
from .backtest import dip_trades, brk_trades, brk_atr_trades, hold_stats, agg


def _stage(C, n):
    s50 = sma(C, 50, n - 1); s150 = sma(C, 150, n - 1); s200 = sma(C, 200, n - 1)
    s2p = sma(C, 200, n - 21) if n >= 221 else None
    if None in (s50, s150, s200):
        return "数据不足", s50, s200
    up = C[-1] > s200 and s50 > s150 and (s2p is None or s200 > s2p)
    dn = C[-1] < s200 and s50 < s150
    return ("Stage2上升" if up else "Stage4下跌" if dn else "过渡/震荡"), s50, s200


def market_state(bars):
    """Volatility-state light, from a precursor study on 39k sample-days (46 tickers × 5y):
    para (parabolic: 20d>+40% & price>50MA×1.25) → BOTH surge & crash odds ×2.3 (violence, trim/tighten);
    brk (below 50MA & 20d<-15%) → crash continuation ×1.38 (don't catch the knife);
    hot (5d>+15%) → crash ×2.2 (don't chase); tight (20d range<12% near highs) → 10d crash ≈0 (safe to stage);
    quiet (vol<20th pct) → calm persists. Priority: para > brk > hot > tight > quiet > neutral."""
    import statistics as _st
    n = len(bars)
    if n < 270:
        return None
    C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    i = n - 1
    s50 = sma(C, 50, i)
    if not s50:
        return None
    ret20 = C[i] / C[i - 20] - 1; ret5 = C[i] / C[i - 5] - 1
    ext = C[i] / s50 - 1
    rng20 = (max(H[i - 19:i + 1]) - min(L[i - 19:i + 1])) / C[i]
    hi252 = max(H[i - 251:i + 1])
    vols = []
    for k in range(i - 252, i + 1):
        if k < 21:
            continue
        rets = [C[m] / C[m - 1] - 1 for m in range(k - 19, k + 1)]
        vols.append(_st.pstdev(rets))
    v = vols[-1]; volp = sum(1 for x in vols if x <= v) / len(vols)
    # vol-normalized thresholds (z-scores vs the ticker's own volatility): a 40% month is
    # normal for a 150%-vol name but parabolic for a 40%-vol name. Fixes false alarms.
    import math as _m
    sig = vols[-1] if vols else 0  # daily sigma (fraction)
    z20 = ret20 / (sig * _m.sqrt(20)) if sig else 0
    z5 = ret5 / (sig * _m.sqrt(5)) if sig else 0
    med_rng = None
    try:
        rngs = [(max(H[k-19:k+1]) - min(L[k-19:k+1])) / C[k] for k in range(i - 251, i + 1)]
        med_rng = _st.median(rngs)
    except Exception:
        pass
    if z20 > 2.5 and C[i] > s50 * (1 + 2 * sig * _m.sqrt(50)): st = "para"
    elif C[i] < s50 and z20 < -1.2: st = "brk"
    elif z5 > 2.2: st = "hot"
    elif med_rng and rng20 < 0.6 * med_rng and C[i] >= hi252 * 0.85: st = "tight"
    elif volp < 0.20: st = "quiet"
    else: st = "neutral"
    return {"st": st, "ret20": round(ret20 * 100), "ret5": round(ret5 * 100),
            "ext": round(ext * 100), "rng20": round(rng20 * 100), "volp": round(volp * 100)}


def diagnose(ticker, bars, name=None, pool_E=None):
    n = len(bars)
    C = [b["c"] for b in bars]; H = [b["h"] for b in bars]; L = [b["l"] for b in bars]
    last = C[-1]
    chg = round((C[-1] / C[-2] - 1) * 100, 2) if n >= 2 else 0
    stage, s50, s200 = _stage(C, n)
    vol = round(annualized_vol(C), 0)
    hi252 = max(H[-252:]) if n >= 252 else max(H)
    pct_from_high = round((last - hi252) / hi252 * 100, 1)

    rec = {"ticker": ticker, "name": name or ticker, "last": round(last, 2), "chg": chg,
           "stage": stage, "vol": vol, "pct_from_high": pct_from_high, "bars": n,
           "state": market_state(bars)}
    # overnight-gap behavior (pre-market playbook): does THIS ticker's >=2% gap-up
    # historically continue (gap-and-go) or fade? Rendered as situational advice
    # ("don't chase / ok to chase + why") whenever the ticker is up/down >=2%.
    import statistics as _sts
    O = [b.get("o", b["c"]) for b in bars]
    ups = []; dns = []
    for k in range(1, n):
        pc, o = C[k - 1], O[k]
        if pc <= 0 or o <= 0:
            continue
        g = o / pc - 1
        if g >= 0.02: ups.append(C[k] / o - 1)
        elif g <= -0.02: dns.append(C[k] / o - 1)
    rec["gap"] = {
        "cont": round(sum(1 for x in ups if x > 0) / len(ups) * 100) if len(ups) >= 20 else None,
        "oc_up": round(_sts.mean(ups) * 100, 1) if len(ups) >= 20 else None, "n_up": len(ups),
        "bounce": round(sum(1 for x in dns if x > 0) / len(dns) * 100) if len(dns) >= 20 else None,
    }

    if n < 250:
        rec.update({"strategy": "avoid", "bucket": "历史不足·新标的",
                    "action": f"日线仅 {n} 根,样本不足,先观察积累,勿套回测结论。",
                    "backtest": {}})
        return rec

    d = agg(dip_trades(bars)); dr = agg(dip_trades(bars, True))
    bk = agg(brk_trades(bars)); ba = agg(brk_atr_trades(bars))
    rec["backtest"] = {"dip": d, "dip_re": dr, "brk": bk, "brk_atr": ba}

    # pick the best strategy. With pool_E (from build): empirical-Bayes shrinkage —
    # shrink each small per-ticker sample toward the pooled prior (K=10) so one lucky
    # trade can't flip a classification. Without pool: raw expectancy (single-ticker mode).
    K = 10
    best, bexp = "avoid", (0.15 if pool_E else 0.10)
    for key, res in (("dip", d), ("dip_re", dr), ("brk", bk), ("brk_atr", ba)):
        if res["n"] >= 5:
            e = res["expectancy_R"]
            if pool_E is not None:
                e = (res["n"] * e + K * pool_E.get(key, 0)) / (res["n"] + K)
            if e > bexp:
                best, bexp = key, e
    rec["strategy"] = best

    # 若主动策略都不占优,但它是强趋势长牛,则改判"长持"(正股·不加杠杆)
    hs = hold_stats(bars); rec["hold_stats"] = hs
    if best == "avoid" and hs["cagr"] >= 25 and pct_from_high > -40 and stage != "Stage4下跌" and s200 and last > s200 * 0.9:
        best = "hold"; rec["strategy"] = "hold"

    if best == "hold":
        s150 = sma(C, 150, n - 1) or s50
        z = sorted({round(s50, 2), round(s150, 2), round(s200, 2)}, reverse=True)  # 越跌越便宜
        rec["signal"] = {"type": "hold", "buy_zones": z,
                         "target": [round(hi252, 2), round(hi252 * 1.15, 2)],
                         "trend_stop": round(s200 * 0.95, 2)}
        zt = " / ".join("$" + str(x) for x in z)
        rec["action"] = (f"长持(正股·不加杠杆):回踩 {zt} 越跌越买(买便宜);目标 ${round(hi252,2)} 前高分批止盈,"
                         f"跌破200日线(~${round(s200*0.95,2)})离场。近{round(n/252,1)}年买持 +{hs['buy_hold_pct']}% 但最大回撤 {hs['max_dd']}%,须扛得住、绝不用杠杆/期权。")
        return rec

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
