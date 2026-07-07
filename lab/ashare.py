"""
A-share (China mainland) specific capabilities that have NO US equivalent.
Read docs/A股量化知识手册.md for the theory behind each. Two groups:

  Pure computation (works offline on bars from datasource):
    board_and_limit, limit_state, turnover_stats, reversal_score
  Network (akshare -> 东财/新浪; needs China-reachable network):
    dragon_tiger, northbound_flow, sentiment_gauge

Design stance: A-shares are long-only, T+1, price-limited, and short-term MEAN-REVERTING
(opposite of US momentum). So the US 'breakout/chase' logic is demoted and a reversal factor
is added. Every function degrades gracefully (returns None/empty) rather than crashing.
"""
import datetime
import statistics


# ---------- board & price limits (涨跌停) ----------
def board_and_limit(code, name=""):
    """Board classification and daily price-limit % for an A-share code.
    Limits: 主板 ±10%, 创业板/科创板 ±20%, 北交所 ±30%, ST/*ST ±5% (主板) / ±20% (创业板 ST)."""
    code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
    is_st = "ST" in (name or "").upper()
    if code.startswith("688"):
        board, lim = "科创板", 20
    elif code.startswith(("300", "301")):
        board, lim = "创业板", 20
    elif code[0] in "48" or code[:3] in ("430", "830", "920"):
        board, lim = "北交所", 30
    else:
        board, lim = "主板", 10
    if is_st:
        lim = 20 if board in ("创业板", "科创板") else 5
        board = "ST·" + board
    return {"board": board, "limit_pct": lim, "st": is_st}


def limit_state(bars, code, name=""):
    """Detect 涨停/跌停/一字板 on the latest bar. A limit-up that is 封死 (locked) means you
    likely COULD NOT have bought — critical: a US 'breakout entry' is often un-fillable here."""
    if not bars or len(bars) < 2:
        return None
    lim = board_and_limit(code, name)["limit_pct"]
    prev, cur = bars[-2]["c"], bars[-1]
    up = round(prev * (1 + lim / 100), 2)
    dn = round(prev * (1 - lim / 100), 2)
    chg = (cur["c"] / prev - 1) * 100
    st = "normal"
    if cur["c"] >= up - 0.01:
        st = "涨停一字" if cur["l"] >= up - 0.01 else "涨停"
    elif cur["c"] <= dn + 0.01:
        st = "跌停一字" if cur["h"] <= dn + 0.01 else "跌停"
    return {"state": st, "chg_pct": round(chg, 2), "limit_pct": lim,
            "limit_up_px": up, "limit_dn_px": dn,
            "tradable_note": ("一字板通常买不进/卖不出,勿把涨停当可成交突破点" if "一字" in st else "")}


# ---------- short-term reversal (反转因子) — THE core A-share alpha vs US momentum ----------
def reversal_score(bars, lookback=21):
    """A-share短期反转: past ~1-month LOSERS tend to bounce, WINNERS tend to give back.
    Returns a score where HIGH = oversold reversal-buy candidate (mirror of US momentum).
    Academic basis: short-horizon reversal is a robust A-share factor (see 知识手册)."""
    if not bars or len(bars) < lookback + 1:
        return None
    ret = (bars[-1]["c"] / bars[-1 - lookback]["c"] - 1) * 100
    # turnover-weighted: high turnover + big drop = strongest reversal setup (retail capitulation)
    tos = [b.get("turnover", 0) for b in bars[-lookback:] if b.get("turnover") is not None]
    avg_to = round(statistics.mean(tos), 2) if tos else None
    # score: more negative past return -> higher reversal score; damped, 0..100
    score = max(0, min(100, round(50 - ret * 1.5)))
    tag = ("超跌反转候选" if ret <= -15 else "偏弱可留意" if ret <= -5
           else "强势·A股短期易回吐(勿追)" if ret >= 15 else "中性")
    return {"past_ret_pct": round(ret, 1), "reversal_score": score,
            "avg_turnover_pct": avg_to, "tag": tag, "lookback": lookback}


def turnover_stats(bars, win=250):
    """换手率 percentile — liquidity/attention factor. Extreme high turnover often marks
    局部顶部 (retail crowding); very low = neglected. Fraction of the last `win` days below now."""
    tos = [b.get("turnover") for b in bars[-win:] if b.get("turnover")]
    if not tos or len(tos) < 20:
        return None
    now = tos[-1]
    pct = round(sum(1 for x in tos if x <= now) / len(tos) * 100, 1)
    return {"turnover_now_pct": now, "turnover_percentile": pct,
            "tag": "换手极高·警惕拥挤见顶" if pct >= 90 else "换手极低·关注度不足" if pct <= 10 else "常态"}


# ---------- network (akshare) — 龙虎榜 / 北向 / 情绪周期 ----------
def _ak():
    import akshare as ak
    return ak


def dragon_tiger(date=None):
    """龙虎榜 (Dragon-Tiger List): daily disclosure of top buy/sell 营业部 seats — the canonical
    way to track 游资 (hot money) and 机构 (institutions). No US equivalent.
    date: 'YYYYMMDD' (default: today). Returns compact rows or [] if unreachable."""
    ak = _ak()
    d = date or datetime.date.today().strftime("%Y%m%d")
    try:
        df = ak.stock_lhb_detail_em(start_date=d, end_date=d)
        if df is None or df.empty:
            return []
        rows = []
        for _, r in df.head(40).iterrows():
            rows.append({k: r[k] for k in df.columns if k in
                         ("代码", "名称", "上榜原因", "涨跌幅", "龙虎榜净买额", "换手率")})
        return rows
    except Exception as e:
        return {"error": str(e)[:80], "note": "龙虎榜需中国可达网络(东财);VPN下常被挡"}


def northbound_flow():
    """北向资金 (Northbound / Stock Connect): foreign money flow via 沪深股通 — a widely-watched
    'smart money' sentiment gauge. Returns recent daily net inflow (亿元) or error."""
    ak = _ak()
    try:
        df = ak.stock_hsgt_north_net_flow_in_em(symbol="北向资金")
        if df is None or df.empty:
            return []
        tail = df.tail(10)
        return [{"date": str(r.iloc[0])[:10], "net_in_yi": round(float(r.iloc[1]) / 10000, 2)}
                for _, r in tail.iterrows()]
    except Exception as e:
        return {"error": str(e)[:80], "note": "北向资金需中国可达网络"}


def sentiment_gauge():
    """市场情绪周期 gauge: 涨停家数 / 跌停家数 / 连板高度 / 炸板率. A-share retail runs in a
    sentiment cycle (冰点→修复→发酵→高潮→退潮); these are its vital signs. No US equivalent."""
    ak = _ak()
    out = {}
    try:
        up = ak.stock_zt_pool_em(date=datetime.date.today().strftime("%Y%m%d"))
        out["涨停家数"] = 0 if up is None else len(up)
        if up is not None and "连板数" in up.columns:
            out["最高连板"] = int(up["连板数"].max()) if len(up) else 0
    except Exception as e:
        out["涨停错误"] = str(e)[:60]
    try:
        zb = ak.stock_zt_pool_zbgc_em(date=datetime.date.today().strftime("%Y%m%d"))
        out["炸板家数"] = 0 if zb is None else len(zb)
    except Exception:
        pass
    if out.get("涨停家数") and out.get("炸板家数") is not None:
        tot = out["涨停家数"] + out["炸板家数"]
        out["炸板率_pct"] = round(out["炸板家数"] / tot * 100, 1) if tot else None
    out["note"] = "需中国可达网络(东财);读法见知识手册'情绪周期'章"
    return out
