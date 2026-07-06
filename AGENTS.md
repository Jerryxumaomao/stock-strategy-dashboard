# AGENTS.md — Operations guide for AI agents driving this skill

Read this BEFORE running anything. Weak models: follow the recipes literally. Strong
models: every rule below carries its WHY — the incident, evidence, or theory behind it —
plus explicit guidance on when deviation is legitimate. Understand the why before you
consider bending anything; if a situation isn't covered, ask the user.

## Why this system is built the way it is (read this first)
The entire value of this tool is that **its numbers are real and its improvements are
evidence-gated**. Its history is a string of plausible ideas that FAILED when tested:
tightening entry rules made results worse; the Chandelier exit lost to the simple SMA50
trail; "NVDA options look fair" was an artifact of trend bias until EV was de-trended.
And ideas that survived testing became rules: per-ticker strategy assignment, ATR-wide
stops for high-vol names, the 37%/z-target exits for fixed-deadline positions.
So the meta-rule is: **intuition proposes, backtests dispose, forward review is the
final judge.** Everything below derives from that.

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

## 🔴 Hard rules — each with its WHY and deviation guidance

1. **Never place trades or move money.**
   *Why:* an agent error here causes irreversible financial loss; analysis errors are
   recoverable, execution errors are not. Also keeps the tool legally clean (not advice).
   *Deviation:* never. Not even with user permission — tell them to execute themselves.

2. **`history/recs-*.json` are immutable; freeze once per day (build handles it).**
   *Why:* forward review is the ONLY unbiased judge of the system (backtests are in-sample
   and survivor-biased). Editing a frozen rec — even to "fix" it — is retroactive
   self-deception: the score stops measuring what the system actually said. Multiple
   freezes per day pseudo-replicate samples and corrupt the statistics.
   *Deviation:* schema upgrades on TODAY's freeze before market close are acceptable
   (same levels, richer fields). Past days: never.

3. **Optimization proposals are never auto-applied; relay with evidence, one change/cycle.**
   *Why:* with dozens of tracked metrics, something always looks significant by chance
   (multiple comparisons). Auto-applying lets noise rewrite the strategy, and silent
   changes destroy the user's trust and the audit trail. One change per cycle keeps
   cause-and-effect attributable. Precedent: the v2 "obvious improvements" (tighter
   entries, break-even stops) all tested WORSE — plausibility is not evidence.
   *Deviation:* none for parameter changes. Re-diagnosis on fresh data is not a
   "change" — it's scheduled refresh (monthly), and even that gets reported.

4. **Never fabricate numbers; report failures and small samples plainly.**
   *Why:* the product IS the numbers. One invented figure poisons every real one, and the
   user makes real-money decisions on them. Small n presented confidently is fabrication's
   polite cousin — a n=2 "3.29R expectancy" once nearly misclassified a ticker until
   shrinkage was added.
   *Deviation:* never. "The fetch failed / n is too small to conclude" is a fully valid answer.

5. **No raw `<` or `>` in free text entering the dashboard payload.**
   *Why:* the browser parses them as HTML tags. This once silently nested every card into
   the previous one and broke the whole page — and it looked like a CSS bug for hours.
   *Deviation:* none needed; full-width ＜＞ or words express the same thing.

6. **Before committing: `py_compile` all modules + one full successful `run.py build`.**
   *Why:* build is the integration test — it exercises fetch, diagnose, radars, render,
   freeze and review in one pass. Skipping it has shipped broken dashboards before.
   *Deviation:* docs-only changes may skip the build, never the commit message honesty.

7. **Match exit rules to the position's time structure.**
   *Why (this is empirical, not aesthetic):* on open-ended stock positions the SMA50 trail
   earned +1.01R because winners could run for months; in fixed 25-day windows (options)
   the trail can't develop and LOST to the z-target 2.33σ√t (+0.31R) and the 37% secretary
   rule (+0.29R, 1,062 samples) — a deadline changes the optimal stopping problem itself.
   *Deviation:* if you have NEW backtest evidence on this repo's data, propose it (rule 3).

8. **Data honesty to the user, every time it's relevant:** yahoo quotes ~15-min delayed;
   option EV is de-trended empirical (assumes history rhymes; survivor bias on big
   winners); state lights predict the *volatility regime*, not direction (the precursor
   study found parabolic states lift BOTH surge and crash odds ~2.3×).
   *Why:* overstating precision is how users get hurt on your watch.
   *Deviation:* never on the caveats; brevity is fine, omission is not.

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
| JS `String.replace` with `$'`/`$&` in replacement | Corrupts the file (inserts the whole suffix). Use a function replacer `replace(x, () => str)` or split/join |
| Emoji above 13.0 (🪞 etc.) | Renders as tofu boxes on Win10. Stick to Emoji ≤12.0 in any HTML output |
| Rendering nullable fields | `'+v.x+'%'` prints "null%" when x is null. Guard every nullable: `(v.x==null?'—':v.x+'%')` |
| Idempotent injectors | Judge success by "pattern EXISTS", not "content changed" — re-running with already-fresh values must not report failure |
| Template payload marker `/*__DATA__*/{}` | Replace the WHOLE marker including its `{}` placeholder. Swapping only the comment leaves `{json}{}` behind = SyntaxError = silently blank dashboard (shipped broken once; build.py now raises if the marker survives) |
| "Was it verified?" answered from memory | Conversation memory gets distorted by context compaction. Every good build appends a timestamped line to `history/build.log` — answer "when was the last good build" from that file, and syntax-check the generated dashboard (`node --check` on the extracted script) rather than trusting a success message |
