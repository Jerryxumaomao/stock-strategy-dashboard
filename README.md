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
python run.py init                     # enter your watchlist
python run.py diagnose NVDA            # one-stock diagnosis
python run.py add PLTR                 # add a stock (auto-diagnosed)
python run.py build                    # rebuild dashboard.html
open dashboard.html                    # (or double-click) — self-contained
```

## What you get, per stock
- **Strategy label**: 📉 dip-buy · 📈 breakout · 📈 breakout·wide-stop · 🏔️ hold · 🚫 avoid (+ reason bucket)
- **Stage & volatility** (SEPA-style trend stage, annualized vol)
- **Backtest**: win rate + expectancy (R) — or, for hold, total return / CAGR / max drawdown
- **Actionable levels**: dip buy zones + stop · breakout trigger + stop · or hold buy-cheap zones + target + trend-exit

## Strategies
| Strategy | For | Entry | Exit | Stop |
|---|---|---|---|---|
| 📉 dip-buy | pulls back cleanly to 50MA | pullback + reversal, 2-3 tranches | half at +2R, trail rest on 50MA | recent swing low |
| 📈 breakout | momentum leaders that gap & run | break above recent 30-40d high | trail on 50MA | breakout base (tight) |
| 📈 breakout·wide-stop | high-vol names whipsawed by tight stops | break above recent high | trail on 50MA | ~2×ATR (adaptive) + half size |
| 🏔️ hold | strong secular uptrend where active trading keeps losing | accumulate cheap on pullbacks to 50/150/200MA | trim at prior high; exit on 200MA break | 200-day MA (**unlevered stock only** — never options) |
| 🚫 avoid | none profitable (crashed / choppy / too new) | — (wait for VCP → breakout, or 200MA reclaim) | — | — |

## Data sources
Default: **Yahoo Finance** (`yfinance`, free, no account). Pluggable — implement `ibkr` /
`tradingview` / your broker in [`lab/datasource.py`](lab/datasource.py) and set `"source"` in
`config.json`.

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
