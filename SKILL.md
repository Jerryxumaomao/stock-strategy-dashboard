---
name: stock-strategy-dashboard
description: >-
  Diagnose a stock watchlist and build a per-stock strategy dashboard. Use when the user
  wants to analyze their stocks, classify each stock into dip-buy / breakout / avoid, backtest
  entry-and-exit rules, get current buy/sell/stop levels per stock, or generate a trading
  dashboard. Also use to add a new ticker (it gets diagnosed automatically). Triggers include:
  "分析我的自选股", "诊断这只股票", "这只票该抄底还是追突破", "帮我建策略看板",
  "build my watchlist dashboard", "which strategy for TICKER", "backtest my stocks",
  "股票策略/选股/回测看板", "add TICKER to my dashboard".
---

# Stock Strategy Dashboard

Diagnoses every stock in a watchlist and assigns the strategy that historically fits it —
**dip-buy**, **breakout**, or **avoid** — then backtests the rules and renders a self-contained
HTML dashboard. Core idea: *different stocks need different strategies; diagnose first, then act.*

## When to use
- User wants their watchlist analyzed / a strategy dashboard built.
- User asks "should I dip-buy or chase the breakout on X?" → run `diagnose`.
- User adds a new stock → run `add` (it gets diagnosed and folded into the dashboard).

## Setup (once)
```
pip install -r requirements.txt      # just yfinance (free Yahoo data, no account)
```
Data source defaults to Yahoo Finance. It is pluggable — see `lab/datasource.py` to wire in
IBKR, TradingView, Alpaca, etc. (change `"source"` in `config.json`).

## Commands (run from the skill directory)
```
python run.py init                 # ask the user for their watchlist, then diagnose + build
python run.py add NVDA MSFT        # add tickers (each auto-diagnosed), rebuild
python run.py remove NVDA          # drop a ticker, rebuild
python run.py build                # rebuild dashboard from config.json
python run.py diagnose NVDA        # print one stock's diagnosis JSON (no dashboard write)
```
Output: `dashboard.html` (self-contained, open in any browser). `config.json` holds the watchlist.

## How to drive it as an agent
1. If the user has no watchlist yet, **ask them which tickers to track**, write them to
   `config.json` (`watchlist`), then run `python run.py build`.
2. To analyze one stock quickly, run `python run.py diagnose TICKER` and summarize the JSON:
   its **strategy** (dip/breakout/avoid), **stage**, **volatility**, backtest **win rate/expectancy**,
   and the concrete **buy/breakout + stop levels** in `signal`.
3. When the user adds a stock, run `python run.py add TICKER` — it is diagnosed automatically.
4. Point the user to the generated `dashboard.html`, and relay the per-stock strategy + levels.

## The strategy logic (what the diagnosis means)
- **📉 dip-buy** — stocks that pull back cleanly to the 50-day MA. Buy the pullback + reversal,
  in 2-3 tranches; exit half at +2R, trail the rest on the 50-day MA. Stop below the recent low.
- **📈 breakout** — momentum leaders that *don't* pull back; they gap and run. Buy the break above
  the recent 30-40 day high (pivot); trail on the 50-day MA. **Do not dip-buy these.**
- **📈 breakout·wide-stop** — high-volatility names that get whipsawed out by a tight stop. Same
  breakout entry, but stop = ~2×ATR (adaptive) and half position size.
- **🏔️ hold** — strong secular uptrends where *active* trading (with stops) keeps losing but the
  stock rips over time (e.g. MRVL/ARM). Best just **held as unlevered stock**: accumulate cheap on
  pullbacks to the 50/150/200-day MAs, trim at the prior high, exit only on a 200-MA break. The
  signal gives the buy-cheap zones + target + trend-exit, and the buy-and-hold return **and max
  drawdown** (you must be able to sit through a large drawdown; **never use options/leverage for this**).
- **🚫 avoid** — none of the above was profitable and it's not a strong uptrend to hold. Reason
  bucket: *parabolic crash* (falling knife — wait for 200-MA reclaim + base), *insufficient history*,
  or *choppy/broken*.

Exit rule (biggest edge, from diagnostics): winners are cut too early with fixed targets, so the
engine **trails on the 50-day MA to let winners run** (roughly doubles expectancy vs a fixed +2R).

## Honest limits (always tell the user)
Backtests are a **reproducible rule proxy**, not strict chanlun/discretionary trading. Results are
in-sample, small samples for some tickers, and **history does not guarantee the future**. The value
is validating *risk-adjusted expectancy and discipline*, not predicting price. **Not investment advice.**
