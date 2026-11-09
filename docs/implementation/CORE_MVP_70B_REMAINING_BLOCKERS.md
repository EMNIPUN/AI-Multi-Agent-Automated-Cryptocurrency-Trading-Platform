# CryptoNova — 70B Remaining Blockers

Development revision is `20261108_0011` on `wmirifmgaftassgrfbyl`. `.env` keeps `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false`.

## Still open

- The ten news events stored before `0010` have no revisions. Historical news backtesting stays invalid. Do not backfill them.
- `/api/v1/backtests/shadow-status` still reports the pre-apply revision and pending list. The database is ahead of that hardcoded payload.
- `/api/v1/signals/status` returns 500 until `SIGNAL_CLOUD_OWNER_USER_ID` or `CRYPTONOVA_TEST_OWNER_USER_ID` is set for Supabase source-of-truth mode. No owner was invented during this apply.
- Signed-in `/news`, `/llm`, `/backtesting`, `/analytics`, `/paper`, and `/agents` were not opened. There is no browser session.
- Paper read API stays disabled. Paper and backtest simulation journals remain SQLite even though development Postgres already has paper tables.
- Two append-only rows remain for test event `70b1evt26a00b9fa389`. The trigger rejects deleting them.
- Managed Supabase backup and point-in-time recovery are still unverified. The recovery point for this apply is the local logical backup `data/backups/70b1_20261108T080402Z`.
- A failed backup attempt wrote a database connection error into the local tool log before the successful backup. Rotate the development database password when convenient. The password is not repeated here.

## Flags that stay off

`AGENT_ALLOW_LIVE=false`. News LLM, advisory, alerts, Telegram, and automatic collection stay at their defaults of false. An OpenAI key is present and no model name is configured. No model call and no Telegram message were sent.
