# CryptoNova — 70A Final Integration Audit

Audit date: 2026-11-08. Read-only database check. No migration was applied. No paid OpenAI call. No Telegram message. No live order.

Development identity: project `wmirifmgaftassgrfbyl`, host `aws-0-ap-southeast-2.pooler.supabase.com`, session pooler, guard `identity_guard=ok`. Alembic current: **`20261108_0007`**.

## Component status

| Component | Implemented | Tests Passed | Database Ready | Runtime Verified | Blocker |
| --- | --- | --- | --- | --- | --- |
| Market → Risk pipeline | Yes | Yes, prior 4A/69C suites; not fully re-run in this pass | Signals may be SQLite when SoT is off | Not re-clicked | None for deterministic rules |
| Paper broker | Yes | Prior paper tests not re-run in this pass | SQLite journal by design | Not re-clicked | SQLite remains the paper journal |
| Portfolio risk | Yes | Covered by paper/risk tests historically | Local journal | Not re-clicked | None for veto rules |
| Analytics | Yes | Prior analytics tests not re-run here | Reads the paper journal | Page not opened | Browser unverified |
| Backtest 68A–68C | Yes | 69E shadow file passed with this audit | Isolated `bt68a_*.sqlite3` | API not re-hit live | SQLite journal stays |
| News foundation 69A | Yes | Included in 44 passed | `news_events` at 0007 | Collector not run live | Provider keys not exercised |
| News persistence 69A.1 | Yes | Live PG test skipped unless `NEWS_PG_INTEGRATION` | Applied through 0007 | Not re-run | Integration skip |
| Alerts 69B | Yes | 69B file passed | Table missing until 0008 | Persistence fail-closed | Apply 0008 |
| News advisory 69C | Yes | Prior 69C file not in this 44 | No extra table | Flag default off | Advisory stays off |
| LLM 69D | Yes | 69D file passed | Audit table missing until 0009 | Fail-closed, no paid call | Apply 0009 and 0011 |
| Shadow 69E | Yes | 69E file passed | Archive missing until 0010 | `historical_news_backtest_valid` false | Old rows stay incomplete |
| Revision writer 70A | Yes | Planning tests passed | Writer no-ops until 0010 | Not exercised on live rows | Apply 0010; no backfill |
| Durable LLM budget 70A | Yes | In-memory and fail-closed tests passed | Ledger missing until 0011 | Runtime uses FailClosedBudget | Apply 0011 |
| Dashboards | Pages exist | Vitest not re-run this pass | n/a | Unsigned pages redirect to sign-in | Signed-in data not opened |

## Runtime flow that the code actually implements

Technical path: Bybit public klines feed Market, Trend, and Momentum. Coordinator scores those outputs. Risk can veto. The decision is stored by the existing signal path and can be simulated by the paper broker. News is not an input unless `evaluate(..., news_advisory_enabled=True)` is passed. The default is false, and `NEWS_AGENT_ADVISORY_ENABLED` is not read automatically by the pipeline. `news_changed_decision` stays false.

News path: providers are optional. The collector validates and classifies, then `PostgresNewsRepository` upserts the latest row. Inside that transaction a savepoint tries `app.news_event_revisions`. If migration `0010` is absent, the savepoint rolls back and the article row can still commit. Status reports `revision_archive_status=archive_unavailable` or `not_written`, and `historical_provenance=incomplete`. Alerts require `0008` and stay disabled by default. Telegram stays disabled. The scheduler starts only when `NEWS_AUTO_COLLECTION_ENABLED` is true.

LLM path: it runs only after a completed technical decision, and only when the flag, key, and model are set. This audit leaves the flag false. If the audit table or the budget ledger is missing, the service returns before any provider call. Recommendations stay advisory.

## Archive behavior

- A new classified event gets revision number 1 when the table exists and no prior row matches.
- A later material change (severity, sentiment, verification, evidence quality, or article hashes) appends the next number.
- `recorded_at_ms` and `revision_available_at_ms` use classification or collection time, not a backdated publication time.
- The same content hash is a duplicate and is not inserted again.
- `ON CONFLICT (event_id, revision_number) DO NOTHING` covers a concurrent insert.
- The migration trigger rejects UPDATE and DELETE.
- Events already stored before `0010` are not backfilled and must not be described as historically complete.

## SQLite that remains

Keep these. Do not delete them in this milestone.

- Paper broker journal (`paper_sqlite_path` / `cryptonova_paper.sqlite3`).
- Backtest journals named `bt68a_*.sqlite3`, isolated from the paper file.
- Offline signal-history tests under `tmp_path` when Supabase SoT is off.

News, alerts, LLM audit, revisions, and the budget ledger refuse SQLite.

Retirement later needs: copy the journals first, prove the same fills and balances on Postgres, keep result hashes reproducible, and keep the SQLite files until that parity is signed off.

## Safety flags left unchanged

`AGENT_ALLOW_LIVE`, `NEWS_LLM_ENABLED`, `NEWS_AGENT_ADVISORY_ENABLED`, `NEWS_ALERTS_ENABLED`, `NEWS_TELEGRAM_ENABLED`, and `NEWS_AUTO_COLLECTION_ENABLED` stay at their code defaults of false. `.env` was not edited. Local `.env` does enable the backtest read and run API gates. Those gates start simulations only.

## Tests in this pass

`44 passed, 0 failed, 0 skipped` across `test_core_70a_audit.py`, `test_core_llm_69d.py`, `test_core_news_69b.py`, `test_core_news_69a.py`, and `test_core_backtest_69e.py`.

The earlier 68/69 regression (94 passed, 1 skipped) predates the writer and budget edits. The skip remains the unset `NEWS_PG_INTEGRATION` test. Live checks of `0008`–`0011` were not run and are not counted as passed.

## Browser check on the already running app

`http://127.0.0.1:3000` was already listening. No second server was started.

Unsigned visits to `/news`, `/llm`, `/backtesting`, `/analytics`, `/paper`, and `/agents` render the page name and then redirect to sign-in. The signed-in dashboards, empty states, and stored records were not opened.

Unauthenticated JSON from the running API:

- `/api/paper/status` is 200. Paper read API is disabled, no database was opened, `execution_allowed` is false, and the label is `SIMULATED / PAPER ONLY`.
- `/api/signals/status` is 200. Mode is `signals_only`. Live trading, private API, and Supabase signal writes are false. The local signal journal is still SQLite (`sqlite_schema_version` 4). The response includes the local storage path. It does not include API keys.
- `/api/news/status`, `/api/llm/status`, and `/api/backtests/shadow-status` return FastAPI `404`. The process that is running does not include those routes. The source tree does. A restart would be required before those pages can be verified, and that restart was not performed.

Page HTML did not contain a database URL or an OpenAI key. A CSS class named `mask-clip` contains the letters `sk-` and is not a credential.
