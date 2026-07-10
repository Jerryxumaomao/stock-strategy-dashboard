#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模板同步器(维护者工具): 把私人 dashboard.html 的渲染层原样搬进开源模板。
  python tools/sync_template.py [私人dashboard路径]   (默认 ../dashboard.html)
做四件事:
  1. 掏空 const DATA={...} → /*__DATA__*/{}(build.py 注入点)
  2. 洗掉个人化内容(告警硬编码→DATA.alerts 数据驱动;标题;私人工作流说明)
  3. 注入「无数据模块标灰」系统 + 首跑提示横幅(开源专属,见 _GREY_JS)
  4. 自检: 恰好1个注入点 / 无余留个人词 / 花括号配对
之后跑 `python run.py build` 用真实数据源填 DATA。
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "..", "dashboard.html")
DST = os.path.join(ROOT, "dashboard_template.html")


def brace_match(s, o):
    d = 0; in_s = False; q = ''
    i = o
    while i < len(s):
        c = s[i]
        if in_s:
            if c == '\\': i += 2; continue
            if c == q: in_s = False
        elif c in ('"', "'"): in_s = True; q = c
        elif c == '{': d += 1
        elif c == '}':
            d -= 1
            if d == 0: return i
        i += 1
    return -1


h = open(SRC, encoding="utf-8").read()

# ── 1. 掏空 DATA ──
k = h.index("const DATA")
o = h.index("{", k)
c = brace_match(h, o)
assert c > 0, "DATA 花括号不配对"
h = h[:k] + "const DATA=/*__DATA__*/{};" + h[c + 1:].lstrip(";")

# ── 2. 洗个人化 ──
# 2a. 告警块: 硬编码(组合集中度/杠杆)→ 全数据驱动 DATA.alerts=[[cls,txt],...]
al_start = h.index("/* alerts")
al_end = h.index('$("alerts").innerHTML', al_start)
al_end = h.index(";", h.index("join", al_end)) + 1
h = h[:al_start] + ('/* alerts —— 全数据驱动(build 按数据情况生成组合级提示) */\n'
                    'const alerts=(DATA.alerts||[]);\n'
                    '$("alerts").innerHTML=alerts.map(al=>`<div class="alert ${al[0]}">${al[1]}</div>`).join("");') + h[al_end:]

# 2b. 标题/称谓
h = h.replace("<title>交易看板</title>", "<title>Stock Strategy Dashboard</title>")
h = h.replace("交易看板", "策略看板")
h = h.replace("私人看板", "策略看板")

# 2c. 私人工作流说明(持仓tab底部 步骤说明含个人数据源细节)→ 通用版
h = re.sub(r"1\. 刷新行情 \+ 情报[^<]*<br>", "1. <b>python run.py build</b> 刷新全部数据(或起 serve.py 用页内🔄按钮)。<br>", h)

# 2d. asOf 行补数据源徽标(渲染时读 DATA.source)
h = h.replace("决策辅助,非投资建议", "决策辅助,非投资建议 · 数据源:<span id=srcTag></span>", 1)

# ── 3. 注入 灰化系统 + 首跑横幅 ──
_GREY = r"""
<script>
/* ===== 开源版: 无数据模块标灰 + 首跑提示(模块保留可见,连接数据源后自动点亮) ===== */
(function(){
  document.getElementById('srcTag')&&(document.getElementById('srcTag').textContent=(DATA.source||'未连接')+(DATA.source==='yahoo'?'(免费·延迟约15分钟)':''));
  var css=document.createElement('style');
  css.textContent='.nodata-host{position:relative}.nodata-ov{position:absolute;inset:0;background:rgba(250,249,245,.78);z-index:6;border-radius:12px;display:flex;align-items:center;justify-content:center;text-align:center}.nodata-ov .nm{font-size:12.5px;color:var(--dim);border:1px dashed var(--border);background:var(--panel);border-radius:10px;padding:10px 16px;max-width:80%;line-height:1.7}.nodata-host>*:not(.nodata-ov){filter:grayscale(.9);opacity:.55}';
  document.head.appendChild(css);
  function off(sel,hint){var el=document.querySelector(sel);if(!el)return;if(!el.offsetHeight)el.style.minHeight='90px';el.classList.add('nodata-host');var ov=document.createElement('div');ov.className='nodata-ov';ov.innerHTML='<div class="nm">🔌 '+hint+'</div>';el.appendChild(ov);}
  var A=DATA.account||{},P=DATA.positions||[];
  if(A.netLiq==null){var ac=document.getElementById('acct');if(ac)ac.innerHTML='';off('#acct','未连接券商接口 — 账户数据不可用。<br>Yahoo 模式无账户;接入 IBKR 等券商后自动显示');}
  if(!P.length){off('#posGrid','无持仓数据 — 在 config.json 填 "positions"(手动)或连接券商接口');off('#dailyReview','每日操作复盘需要持仓数据');off('#auditBox','执行审计需要成交记录(history/trades.json + run.py audit)');}
  if(!(DATA.intel||[]).length) off('#intelBox','情报流未接入 — 需新闻数据源(可自行接入 RSS/newsroom;见 README)');
  if(!(DATA.research||[]).length) off('#researchBox','研报模块未接入 — 需研报摘要数据源');
  if(!(DATA.options&&(DATA.options.scan||[]).length)) off('#tab-opt .section-title~*,#tab-opt','期权扫描需要期权链数据 — config.json 设 "top10": true(yahoo链,较慢)或接券商实时链');
  if(!(DATA.darkprints&&DATA.darkprints.rows&&DATA.darkprints.rows.length)) off('#darkprintsBox','暗盘大单需要 TWS 本地接口(可选) — run.py darkprints');
  if(!(DATA.extended&&DATA.extended.rows&&DATA.extended.rows.length)) off('#extBox','盘前盘后行情需要 TWS 本地接口(可选) — run.py extended');
  if(!(DATA.movers&&(DATA.movers.gainers||DATA.movers.rows))) off('#moversBox','全市场异动:python run.py movers 后自动点亮');
  if(!(DATA.dark&&(DATA.dark.rows||[]).length)) off('#darkBox','暗盘SVR(FINRA免费):python run.py darkpool 后自动点亮');
  if(DATA.meta&&DATA.meta.firstRun){
    var b=document.createElement('div');
    b.style.cssText='background:#f8f1df;border:1px solid var(--yellow);border-radius:10px;padding:12px 16px;margin:10px 0;font-size:13px;line-height:1.8';
    b.innerHTML='🔌 <b>尚未连接数据源。</b>请先运行 <code>python run.py init</code>:①选择数据源(有券商接口选券商;没有则用默认 <b>Yahoo 免费数据</b>)②输入你要看的标的代码(如 NVDA MSFT AAPL)。完成后本页所有模块将用你的数据点亮。';
    var host=document.querySelector('.wrap')||document.body;host.insertBefore(b,host.firstChild.nextSibling);
  }
})();
</script>
"""
h = h.replace("</body>", _GREY + "\n</body>")

# ── 4. 自检 ──
assert h.count("/*__DATA__*/{}") == 1, "注入点数量异常"
for bad in ("netLiq\":3", "Jerry", "jerryxu", "PDT已解除"):
    assert bad not in h, f"发现个人残留: {bad}"
open(DST, "w", encoding="utf-8").write(h)
print(f"✅ 模板已同步: {len(h)} 字符 → dashboard_template.html(注入点1个·个人内容已洗·灰化系统已注入)")
