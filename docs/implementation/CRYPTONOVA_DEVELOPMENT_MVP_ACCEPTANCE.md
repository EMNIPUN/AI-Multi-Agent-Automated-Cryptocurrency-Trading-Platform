# CryptoNova — Development MVP Acceptance

**Not accepted as a finished Supabase-only development MVP.**

Accepted as done on development project `wmirifmgaftassgrfbyl`:

- Revision `20261108_0011` is applied.
- Alert, LLM audit, revision, and budget tables exist with the reviewed constraints, RLS, and the append-only trigger.
- New news classifications can append revisions. Duplicate material does not.
- LLM budget accounting is durable and fail-closed. The feature flag stays off.
- Shadow status tells the truth: the revision is `0011`, and historical news backtesting is not valid.
- Live trading stays off.

Not accepted:

- Historical news performance for the 10 events that have no revisions.
- Signed-in `/news`, `/llm`, `/backtesting`, `/analytics`, `/paper`, and `/agents`.
- Signal status, until an owner id is chosen by the operator.
- Replacement of `bt68a_*.sqlite3` backtest journals.
- A claim that paper analytics on the dashboard match the three Postgres sessions. The read API is off.
- Production readiness, profitability, or autonomous LLM execution.

The next safe step is an operator decision on the signal owner id, then a signed-in pass. A Postgres backtest journal needs a separate migration approval and a parity suite. Do not delete the SQLite journals before that parity exists.
