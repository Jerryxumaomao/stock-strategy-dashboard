# AGENTS.md — Operations guide for AI agents driving this skill

Read this BEFORE running anything. Follow the recipes; don't improvise. If something
isn't covered here, ask the user instead of guessing.

## What this is
A stock/options strategy dashboard engine. It diagnoses every ticker in a watchlist,
assigns the strategy that historically fits it (dip-buy / breakout / breakout-wide-stop /
hold / avoid), backtests the rules, renders a self-contained `dashboard.html`, and keeps a
forward-review loop that scores its own recommendations over time.

## File map
```
run.py                 CLI entry (init/add/remove/build/review/options/audit/movers/darkpool/darkprints/extended)
config.json            watchlist + source + capital + risk_pct
lab/datasource.py      pluggable data (yahoo default; ibkr/tradingview are stubs to wire)
lab/diagnose.py        per-ticker: SEPA stage, vol, strategy pick (shrinkage), state light, gap stats, levels
lab/backtest.py        entry/exit engines (dip/breakout/ATR-wide) + hold stats
lab/options.py         vol cone, implied-vs-realized, 4-bucket contract scoring (de-trended EV)
lab/review.py          freeze / snapshot / score / propose (self-improvement loop)
lab/audit.py           discipline score: user's real trades vs frozen recs
lab/movers.py|darkpool.py            market-wide radar / FINRA dark-pool SVR (free)
lab/darkprints.py|extended.py        optional TWS modules (graceful skip without TWS)
dashboard_template.html              render template (payload injected at /*__DATA__*/)
history/               recs-*.json (frozen recommendations), snap-*.json, trades.json — user data, gitignored
```

## 🔴 Hard rules
1. **Never place trades or move money.** This tool analyzes; the user executes. Every
   summary you give ends with a not-investment-advice note.
2. **`history/recs-*.json` are immutable.** They are the ground truth for forward review.
   Freezing is once per day and idempotent (build handles it) — never hand-edit or re-freeze.
3. **Proposals are never auto-applied.** If `review`/`build` prints optimization proposals,
   relay them verbatim with the evidence and ask the user to approve. One change per cycle.
4. **Never fabricate numbers.** Every figure you report must come from actual script output.
   If a fetch fails, a sample is small, or data is missing — say so plainly.
5. **Free text going into the dashboard payload must not contain raw `<` or `>`**
   (breaks the HTML). Use full-width ＜＞ or words.
6. **Before committing code changes:** `python -m py_compile run.py lab/*.py` then a full
   `python run.py build` must succeed end-to-end.
7. **Match exit rules to time structure** (documented in README): options / fixed-deadline
   positions use the z-target (2.33σ√t) or 37% secretary rule; open-ended stock positions
   use the SMA50 trail. Don't swap them.
8. **Data honesty to the user:** yahoo quotes are ~15-min delayed; option EV is de-trended
   empirical (assumes history rhymes; survivor bias on big winners); state lights predict
   the *volatility regime*, not direction.

## Recipes
### First-time setup (`init` or when user has no config)
1. Ask which **data source**: free Yahoo (delayed ~15 min) vs their broker's real-time feed
   (better, especially for options, but market-data subscriptions **may incur fees**;
   needs wiring in `lab/datasource.py`). Default yahoo.
2. Ask which **tickers** to track, and optionally their **capital / risk % per trade**
   (defaults 10000 / 1.5 — drives the position-size lines).
3. `python run.py build` → open `dashboard.html`. Summarize per-ticker strategy + levels.

### Daily refresh
- Full: `python run.py build` (refetch + rediagnose + radars + freeze + review).
- Intraday repeat: `python run.py review` (light: snapshot + score + proposals only).
- After either: report account-relevant highlights — strategy/state changes, gap advice
  that fired (≥2% moves), market gate color, discipline/review scores, any proposals.

### Add / analyze a ticker
`python run.py add TICK` (auto-diagnosed) or `python run.py diagnose TICK` (print-only).
Relay: strategy + why, state light, actionable levels, backtest n/win/expectancy —
including honesty about small n.

### Options question ("which option should I buy?")
`python run.py options TICK`. Relay bucket candidates WITH their gates: vol-tax > 1.5 →
spreads only, no naked buys; lottery bucket only if `lottery_admitted`; note EV caveats.

### Execution audit
User exports fills to `history/trades.json` (format in `lab/audit.py` docstring) →
`python run.py audit` → relay the discipline score and each violating trade with its rule.

## Known pitfalls
| Pitfall | Handling |
|---|---|
| FINRA download 403 | urllib needs a User-Agent header (already in code) |
| TWS modules can't connect | Normal without TWS running/API enabled — skip gracefully, tell user the one-time setup (TWS → Global Config → API → Enable Socket Clients) |
| Weekend/holiday quotes NaN | Filtered in code; empty extended table is normal |
| `yf.screen` missing | Older yfinance — movers section degrades; suggest `pip install -U yfinance` |
| Tiny backtest samples (n<5) | Strategy falls to avoid/hold checks; never present n=1-2 stats as meaningful |
| New IPOs (<250 bars) | Diagnosed as insufficient-history; don't force strategies onto them |
