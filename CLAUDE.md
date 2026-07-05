# stock-strategy-dashboard

**Before doing anything here, read `AGENTS.md`** — hard rules + step-by-step recipes +
known pitfalls. Follow it exactly; ask the user when something isn't covered.

Top rules (full list in AGENTS.md):
- Never place trades. Analysis only; outputs are not investment advice.
- `history/recs-*.json` are immutable ground truth; freeze is once/day, idempotent.
- Optimization proposals are relayed to the user for approval — never auto-applied.
- Never fabricate numbers; report failures and small samples honestly.
- Before committing: `python -m py_compile run.py lab/*.py` + a successful `python run.py build`.
