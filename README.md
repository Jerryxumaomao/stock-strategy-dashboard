# 📊 Stock Strategy Dashboard (Agent Skill)

Diagnose every stock in your watchlist and let the data pick the strategy — **dip-buy**,
**breakout**, or **avoid** — then backtest it and render a clean, self-contained dashboard.

Built to run **inside Claude Code or Codex as a skill**: your agent asks for your watchlist,
diagnoses each stock, assigns a strategy, and builds the dashboard for you. Also works as a
plain Python CLI.

> **Core idea:** different stocks need different strategies. A momentum leader (NVDA/MU) that only
> gaps and runs must be **bought on breakouts**, not dip-bought. A stock that pulls back cleanly
> (CIEN/AMAT) is a **dip-buy**. A whippy 100%-vol name is best **avoided** until it tightens.
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
- **Strategy label**: 📉 dip-buy · 📈 breakout · 🚫 avoid (+ reason bucket)
- **Stage & volatility** (SEPA-style trend stage, annualized vol)
- **Backtest**: win rate + expectancy (R) for the assigned strategy
- **Actionable levels**: dip buy zones + stop, or breakout trigger + stop

## Strategies
| Strategy | For | Entry | Exit | Stop |
|---|---|---|---|---|
| 📉 dip-buy | stocks that pull back to 50MA | pullback to 50MA + reversal, 2-3 tranches | half at +2R, trail rest on 50MA | recent swing low |
| 📈 breakout | momentum leaders that gap & run | break above recent 30-40d high | trail on 50MA | breakout base |
| 🚫 avoid | neither rule profitable | — (wait for VCP → breakout, or 200MA reclaim) | — | — |

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
