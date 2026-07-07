"""
A-share market-wide research tools (曾因个人看板铁律6被排除,ashare 分支补齐)。
全部经 akshare;多通道优选未被墙的 host(THS/新浪/百度),东财被 VPN 挡时优雅降级。
每个函数返回结构化 dict/list,失败返回 {"error","note"} 而非崩溃。

  market_review()        #2 盘后复盘: 指数 + 市场宽度(涨跌家数) + 估值温度 + 情绪
  event_risk(codes)      #3 事件风险: 解禁 + 质押(减持best-effort)
  industry_rotation()    #4 行业轮动: 板块涨跌/量能排名 + 领涨领跌
  lhb_factor()           #5 龙虎榜因子: 个股上榜统计(次数/净买/席位) 排名
  stock_dossier(code)    #6 个股档案: 财务摘要 + 估值(PE/PB TTM 分位)
  screener(...)          #7 选股筛选器: 全A快照按价格/涨跌/成交额筛,可接 dossier 深研

务必配合 docs/A股量化知识手册.md 理解读法;决策辅助非投资建议。
"""
import datetime
import statistics


def _ak():
    import warnings
    warnings.filterwarnings("ignore")
    import akshare as ak
    return ak


def _err(e):
    return {"error": str(e)[:90], "note": "该接口需中国可达网络(东财push2常被VPN挡;THS/新浪/百度多通道已尽力)"}


def _today():
    return datetime.date.today().strftime("%Y%m%d")


# ---------- #7 选股筛选器 ----------
def screener(price=None, chg=None, min_amount_yi=None, exclude_st=True, limit=30):
    """全A快照筛选(新浪源,不被墙)。price=(low,high)价格带; chg=(low,high)当日涨跌幅%;
    min_amount_yi=最小成交额(亿)。返回过滤后列表(按成交额降序);再用 stock_dossier 深研基本面。"""
    ak = _ak()
    try:
        df = ak.stock_zh_a_spot()
    except Exception as e:
        return _err(e)
    def col(*names):
        for n in names:
            if n in df.columns:
                return n
        return None
    c_code, c_name = col("代码", "symbol"), col("名称", "name")
    c_px, c_chg = col("最新价", "trade"), col("涨跌幅", "changepercent")
    c_amt = col("成交额", "amount")
    rows = []
    for _, r in df.iterrows():
        try:
            nm = str(r[c_name])
            if exclude_st and ("ST" in nm.upper() or "退" in nm):
                continue
            px = float(r[c_px]); cg = float(r[c_chg]) if c_chg else 0
            amt_yi = (float(r[c_amt]) / 1e8) if c_amt else None
            if price and not (price[0] <= px <= price[1]):
                continue
            if chg and not (chg[0] <= cg <= chg[1]):
                continue
            if min_amount_yi and (amt_yi is None or amt_yi < min_amount_yi):
                continue
            rows.append({"code": str(r[c_code])[-6:], "name": nm, "px": round(px, 2),
                         "chg_pct": round(cg, 2), "amount_yi": round(amt_yi, 2) if amt_yi else None})
        except Exception:
            continue
    rows.sort(key=lambda x: -(x["amount_yi"] or 0))
    return {"n_universe": len(df), "n_hit": len(rows), "rows": rows[:limit],
            "filters": {"price": price, "chg": chg, "min_amount_yi": min_amount_yi, "exclude_st": exclude_st}}


# ---------- #6 个股档案 ----------
def stock_dossier(code):
    """个股档案: 财务摘要(营收/净利/ROE等) + 估值(PE/PB TTM 近一年分位)。"""
    ak = _ak()
    code = "".join(c for c in str(code) if c.isdigit()).zfill(6)
    out = {"code": code}
    try:
        fa = ak.stock_financial_abstract(symbol=code)
        # 取最近两期关键指标
        keep = ("归母净利润", "营业总收入", "净资产收益率(ROE)", "销售毛利率", "资产负债率", "每股收益")
        cols = [c for c in fa.columns if c not in ("选项", "指标")]
        recent = cols[:2] if len(cols) >= 2 else cols
        fin = {}
        for _, r in fa.iterrows():
            ind = str(r.get("指标", ""))
            if any(k in ind for k in keep):
                fin[ind] = {p: (None if str(r[p]) == "nan" else r[p]) for p in recent}
        out["financials"] = fin
        out["periods"] = recent
    except Exception as e:
        out["financials_error"] = _err(e)
    for ind, key in [("市盈率(TTM)", "pe_ttm"), ("市净率", "pb")]:
        try:
            v = ak.stock_zh_valuation_baidu(symbol=code, indicator=ind, period="近一年")
            vals = [float(x) for x in v["value"].tolist() if str(x) not in ("nan", "None")]
            if vals:
                now = vals[-1]
                pct = round(sum(1 for x in vals if x <= now) / len(vals) * 100, 1)
                out[key] = {"now": round(now, 2), "pct_1y": pct,
                            "tag": "估值高位" if pct >= 80 else "估值低位" if pct <= 20 else "中位"}
        except Exception:
            pass
    return out


# ---------- #4 行业轮动 ----------
def industry_rotation(top=8):
    """行业轮动: 同花顺行业板块当日涨跌/量能,排名领涨领跌(资金流向的方向)。"""
    ak = _ak()
    try:
        df = ak.stock_board_industry_summary_ths()
    except Exception as e:
        return _err(e)
    def col(*names):
        for n in names:
            if n in df.columns:
                return n
        return None
    c_name, c_chg = col("板块", "name"), col("涨跌幅", "涨跌幅(%)")
    rows = []
    for _, r in df.iterrows():
        try:
            rows.append({"industry": str(r[c_name]), "chg_pct": float(r[c_chg])})
        except Exception:
            continue
    rows.sort(key=lambda x: -x["chg_pct"])
    return {"n": len(rows), "领涨": rows[:top], "领跌": rows[-top:][::-1],
            "note": "领涨板块=当日资金方向;A股板块轮动快,连续领涨才是主线,单日勿追高"}


# ---------- #5 龙虎榜因子 ----------
def lhb_factor(period="近一月", top=25):
    """龙虎榜因子: 个股上榜统计(上榜次数/净买额/龙虎榜后涨跌),按净买额排名——
    追踪哪些票被游资/机构反复运作。period ∈ {近一月,近三月,近六月,近一年}。"""
    ak = _ak()
    try:
        df = ak.stock_lhb_stock_statistic_em(symbol=period)
    except Exception as e:
        return _err(e)
    def col(*names):
        for n in names:
            if n in df.columns:
                return n
        return None
    c_code, c_name = col("代码"), col("名称")
    c_cnt = col("上榜次数", "龙虎榜上榜次数", "上榜次数总计")
    c_net = col("龙虎榜净买额", "净买额", "累积买入额")
    rows = []
    for _, r in df.iterrows():
        try:
            rows.append({"code": str(r[c_code]), "name": str(r[c_name]),
                         "上榜次数": int(r[c_cnt]) if c_cnt else None,
                         "净买额": (round(float(r[c_net]) / 1e8, 2) if c_net else None)})
        except Exception:
            continue
    rows.sort(key=lambda x: -(x["净买额"] or -1e9))
    return {"period": period, "n": len(rows), "净买额榜": rows[:top],
            "note": "龙虎榜=游资/机构席位透明窗口;高频上榜+大净买=被资金反复运作,但打板风险高勿盲从"}


# ---------- #3 事件风险 ----------
def event_risk(codes=None, days_ahead=30):
    """事件风险: 未来解禁(全市场汇总或指定票) + 市场质押水平。解禁=潜在抛压。"""
    ak = _ak()
    out = {}
    start, end = _today(), (datetime.date.today() + datetime.timedelta(days=days_ahead)).strftime("%Y%m%d")
    try:
        rel = ak.stock_restricted_release_summary_em(symbol="全部股票", start_date=start, end_date=end)
        rows = []
        for _, r in rel.head(20).iterrows():
            rows.append({k: (str(r[k]) if hasattr(r[k], "strftime") else r[k]) for k in rel.columns
                         if k in ("解禁时间", "当日解禁股票家数", "实际解禁市值", "解禁数量")})
        out["解禁"] = {"未来{}天".format(days_ahead): rows, "note": "解禁=限售股上市流通=潜在抛压;临近解禁的高解禁比例票注意"}
    except Exception as e:
        out["解禁"] = _err(e)
    try:
        pl = ak.stock_gpzy_profile_em()
        last = pl.iloc[0] if len(pl) else None
        if last is not None:
            out["市场质押"] = {k: last[k] for k in pl.columns[:5]}
    except Exception as e:
        out["市场质押"] = _err(e)
    return out


# ---------- #2 盘后复盘 ----------
def market_review():
    """盘后复盘: 市场宽度(涨跌家数,新浪全A) + 情绪(涨停/连板/炸板) + 估值温度(全A中位PE via 百度示例)。"""
    ak = _ak()
    out = {}
    try:
        sp = ak.stock_zh_a_spot()
        chg_col = "涨跌幅" if "涨跌幅" in sp.columns else "changepercent"
        chgs = [float(x) for x in sp[chg_col].tolist() if str(x) not in ("nan", "None")]
        up = sum(1 for x in chgs if x > 0); dn = sum(1 for x in chgs if x < 0); flat = len(chgs) - up - dn
        out["市场宽度"] = {"上涨": up, "下跌": dn, "平盘": flat, "总数": len(chgs),
                       "涨跌比": round(up / dn, 2) if dn else None,
                       "读法": "涨跌比>1.5普涨/<0.6普跌;宽度背离(指数涨但跌多)=分化警惕"}
    except Exception as e:
        out["市场宽度"] = _err(e)
    try:
        from . import ashare as A
        out["情绪周期"] = A.sentiment_gauge()
    except Exception as e:
        out["情绪周期"] = _err(e)
    return out
