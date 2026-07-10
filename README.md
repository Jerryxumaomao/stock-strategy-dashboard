# 📊 Stock Strategy Dashboard (Agent Skill)

Diagnose every stock in your watchlist and let the data pick the strategy — **dip-buy**,
**breakout** (incl. an ATR-wide-stop variant for high-vol names), **long-hold**, or
**avoid** — then backtest it and render a clean, self-contained dashboard.

Built to run **inside Claude Code or Codex as a skill**: your agent asks for your watchlist,
diagnoses each stock, assigns a strategy, and builds the dashboard for you. Also works as a
plain Python CLI.

> **Core idea:** different stocks need different strategies. A momentum leader (NVDA/MU) that only
> gaps and runs must be **bought on breakouts**, not dip-bought. A stock that pulls back cleanly
> (CIEN/AMAT) is a **dip-buy**. A high-vol name whipsawed by tight stops needs an **ATR-wide stop**.
> A strong secular uptrend where active trading keeps losing (MRVL/ARM) is often best just
> **held** (accumulate cheap on dips, unlevered). A broken/choppy name is **avoided** until it heals.
> The tool diagnoses which is which — per stock — from 5 years of history.

## Quick start

### As a skill (Claude Code / Codex)
1. Clone into your skills folder, e.g. `~/.claude/skills/stock-strategy-dashboard/`
   (Codex: place where your agent reads skills, or just point it at `SKILL.md`).
2. Ask your agent: **"分析我的自选股 NVDA MU TSM CIEN"** or **"build my strategy dashboard"**.
   The agent installs deps, diagnoses each ticker, and opens `dashboard.html`.

### As a CLI
```bash
pip install -r requirements.txt        # only yfinance (free Yahoo data)
python run.py init                     # ①选数据源(无券商接口→默认 Yahoo 免费)②输入你的标的代码
python run.py diagnose NVDA            # one-stock diagnosis
python run.py add PLTR                 # add a stock (auto-diagnosed)
python run.py build                    # rebuild dashboard.html
python run.py options NVDA             # options: vol cone + implied-vs-realized + 4-bucket
                                       #   candidates (lottery gated, 45-90d main, LEAPS)
python run.py audit                    # discipline score: your real trades vs frozen recs
open dashboard.html                    # (or double-click) — self-contained
```

### 看板模块与数据源(哪些开箱即用,哪些要接数据)
看板与作者私版**同一渲染层**:信号灯(🟢可买/🟡等待/🔴回避)、每卡操作建议、综合评分(质量×时机
+逐项拆解弹窗)、缠论结构引擎(MA/摆动/中枢/买卖区/止损,确定性计算)、每日操作复盘。
**没有数据的模块不会消失——保留但标灰**,并提示需要连接哪种数据接口;接上后自动点亮:

| 模块 | Yahoo 免费数据 | 需要额外接入 |
|---|---|---|
| 自选诊断/缠论/评分/操作建议/买卖区 | ✅ 开箱即用 | — |
| 大盘开关/相关簇/财报日历/暗盘SVR/异动 | ✅(Yahoo/FINRA 免费) | — |
| 持仓卡+每日复盘 | 手动:config.json 填 `"positions":[{"sym":"NVDA","qty":10,"avgCost":100}]` | 或接券商接口 |
| 账户(净值/杠杆/购买力) | ❌ 标灰 | 券商接口(如 IBKR) |
| 期权 Top10 扫描 | config 设 `"top10": true`(Yahoo 链,较慢) | 券商实时链更准 |
| 盘前盘后/暗盘大单 | ❌ 标灰 | 本地 TWS API(可选:`run.py extended / darkprints`) |
| 情报流/研报 | ❌ 标灰 | 自行接入新闻/研报源(或让你的 agent 定期写入) |

### One-click refresh (in-page button)
Prefer clicking over re-running `build`? Serve the dashboard locally and use the top-right
**🔄 refresh** button:
```bash
python serve.py                        # starts a local server + opens the browser (or double-click serve.bat on Windows)
```
Click 🔄 → it runs `run.py build` in the background, a progress bar advances per diagnosed
ticker, and the page auto-reloads when done. The button only works over the local server
(http); opened as a bare file (`file://`) it greys out. Failures show honestly on the bar,
never faked.
Set `capital` and `risk_pct` in `config.json` — every signal then shows a **position size**
(risk budget ÷ stop distance). For `audit`, export your fills to `history/trades.json`
(format documented in `lab/audit.py`) — execution drift, not signal quality, is usually
the biggest leak, and this makes it a number.

## What you get, per stock
- **Strategy label**: 📉 dip-buy · 📈 breakout · 📈 breakout·wide-stop · 🏔️ hold · 🚫 avoid (+ reason bucket)
- **Market-state light** (see below): 🔥 parabolic · 🔥 hot · ⚠️ breakdown · 🛡️ tight base · 😴 quiet · neutral —
  with a contextual note **inside the entry/trim module explaining why to act or wait right now**
- **Stage & volatility** (SEPA-style trend stage, annualized vol)
- **Backtest**: win rate + expectancy (R) — or, for hold, total return / CAGR / max drawdown
- **Actionable levels**: dip buy zones + stop · breakout trigger + stop · or hold buy-cheap zones + target + trend-exit

## Market-state lights (precursor study)
From a 39k sample-day study (46 tickers × 5y, 10-day forward window; baseline: surge ≥+20% 9.3%, crash ≤-20% 3.4%):

| State (observable today) | Surge lift | Crash lift | What the dashboard tells you |
|---|---|---|---|
| 🔥 parabolic (20d>+40% & price>50MA×1.25) | 2.4× | **2.3×** | violence both ways → trim + tighten stops, never add; entries paused |
| 🔥 hot (5d>+15%) | 1.9× | 2.2× | don't chase; holders may bank some |
| ⚠️ breakdown (below 50MA & 20d<-15%) | 1.4× | **1.4×** | falling knife → entries paused until 50MA reclaimed |
| 🛡️ tight base near highs (20d range<12%) | 0.15× | **≈0** | safest place to stage a position before a breakout |
| 😴 quiet (vol<20th pct) | 0.7× | 0.55× | calm persists; execute plan unhurried |

Key insight: **price signals predict the volatility state, not the direction.** Caveats: no volume data,
overlapping samples, mostly one bull regime, survivor-biased ticker pool — crash lifts will be worse in a bear.

## Situational gap advice (盘前/大涨喊话)
Each diagnosis includes the ticker's own 15y overnight-gap behavior (continuation vs fade). Whenever a
ticker is up/down ≥2%, its card speaks directly: **"don't chase — this name's gap continuation is only
40%, chasing averaged -0.6%"** or **"ok to go with it — 60% continuation, stop below the open"**. No
lookup tables; the advice appears exactly when the situation does.

## Optimal-stopping exit for options (secretary rule)
For positions with a HARD deadline (options), a fixed-horizon backtest (1,062 samples, 25-day windows)
found two exits that beat the SMA50 trail: **z-target** (take profit when the move hits 2.33σ√t, ≈99th
percentile — +0.31R) and the **37% secretary rule** (observe the first 37% of remaining life recording
the peak; sell on the first new high after — +0.29R, 44% win vs trail's +0.22R/31%). Open-ended stock
positions keep the SMA50 trail (it wins +1.01R when winners can run for months). Match the exit rule
to the position's time structure.

## Strategies
| Strategy | For | Entry | Exit | Stop |
|---|---|---|---|---|
| 📉 dip-buy | pulls back cleanly to 50MA | pullback + reversal, 2-3 tranches | half at +2R, trail rest on 50MA | recent swing low |
| 📈 breakout | momentum leaders that gap & run | break above recent 30-40d high | trail on 50MA | breakout base (tight) |
| 📈 breakout·wide-stop | high-vol names whipsawed by tight stops | break above recent high | trail on 50MA | ~2×ATR (adaptive) + half size |
| 🏔️ hold | strong secular uptrend where active trading keeps losing | accumulate cheap on pullbacks to 50/150/200MA | trim at prior high; exit on 200MA break | 200-day MA (**unlevered stock only** — never options) |
| 🚫 avoid | none profitable (crashed / choppy / too new) | — (wait for VCP → breakout, or 200MA reclaim) | — | — |

## Forward review & self-improvement loop (复盘优化)
Every `build` automatically:
1. **Freezes** the day's recommendations once (`history/recs-DATE.json`, idempotent — rerunning
   intraday never duplicates samples, it only tightens that day's hi/lo snapshot);
2. **Snapshots** each ticker's latest daily bar (`history/snap-DATE.json`, keyed by the bar's own
   date so holidays never create empty cohorts);
3. **Scores** every past cohort against what actually happened: forward return by strategy group,
   buy-zone touch rate, stop-breach-after-touch rate, breakout fire rate;
4. **Proposes** parameter changes ONLY past strict evidence gates (same issue in ≥2 non-overlapping
   cohorts, ≥30 samples, cohorts ≥5 forward days) — and **never auto-applies**: proposals are
   printed for the user to approve, so the system improves without silently overfitting itself.

Run `python run.py review` for a lightweight intraday refresh (snapshot + score + proposals,
no rebuild). The more often you run it, the more precise that day's hi/lo record becomes.

Also in every build: an **earnings radar** (next 3 weeks, with the straddle-window guidance)
and — with `"top10": true` in config — a **daily Top-10 options ranking** across the pool
(real chain quotes, de-trended EV, shown even when everything is expensive; gates attached).
Standalone: `python run.py top10`.

Built-in proposal gates: buy zones posted too deep (price ran away untouched) · zones/stops too
tight (filled then stopped) · strategy discrimination broken (active picks underperform the avoid
bucket → re-diagnose the universe).

## Data sources — pick your trade-off at `init`
`python run.py init` asks you to choose:

| Source | Cost | Quality |
|---|---|---|
| **yahoo** (default) | Free, no account | ~15-min delayed quotes; option chains OK but not pristine |
| **broker (ibkr / tradingview / yours)** | Broker account; real-time market-data subscriptions **may incur fees** (e.g. IBKR OPRA/US bundles, a few $/month) | Real-time quotes, live option chains / IV / order book — best for the options module |

Recommendation: start free on Yahoo to try everything; wire in your broker via
[`lab/datasource.py`](lab/datasource.py) (implement one function, set `"source"` in
`config.json`) when you want real-time precision — especially for options scanning.

## Layout
```
SKILL.md               # agent skill definition (how/when to use)
run.py                 # CLI: init / add / remove / build / diagnose
lab/                   # engine: datasource, indicators, backtest, diagnose, build
dashboard_template.html# self-contained dashboard template
config.json            # your watchlist + data source
```

## ⚠️ Disclaimer
Research/education only, **not investment advice**. Backtests are rule-based proxies; in-sample,
small samples for some tickers, and **past performance ≠ future results**. Trade at your own risk.

MIT © 2026
