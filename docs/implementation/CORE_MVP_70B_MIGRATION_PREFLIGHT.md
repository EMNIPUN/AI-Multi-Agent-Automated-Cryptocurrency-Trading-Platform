# CryptoNova — 70B Migration Preflight

Read-only check on 2026-11-08. No `alembic upgrade` was run. Credentials were not printed. `.env` was not modified.

## Identity

| Check | Result |
| --- | --- |
| `CRYPTONOVA_DB_TARGET` | `development` |
| `CRYPTONOVA_DEV_PROJECT_REF` | `wmirifmgaftassgrfbyl` |
| Connection project ref | `wmirifmgaftassgrfbyl` |
| Host | `aws-0-ap-southeast-2.pooler.supabase.com` |
| Database name | `postgres` |
| Pooler | session pooler |
| Role prefix | `postgres` (privileged; bypasses RLS) |
| `CRYPTONOVA_USE_DATABASE_URL_AS_DEV` | `true` |
| `DEV_DATABASE_URL` | unset |
| `CRYPTONOVA_PROD_PROJECT_REFS` | unset |
| Production target selected | no |
| Live `SELECT 1` and `app.alembic_version` | succeeded |
| Alembic revision | **`20261108_0007`** (one row) |
| `.env` `CRYPTONOVA_ALLOW_DEV_MIGRATIONS` | **`false`** |

The first probe inherited a process value of `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes`. `load_dotenv(..., override=False)` does not replace an existing process value. A second probe loaded `.env` with override and confirmed the file gate is false. That inherited value is not approval to migrate. The file was left false.

`OPENAI_API_KEY` is present in the environment. `NEWS_LLM_ENABLED` is unset, so the code default remains false. No model call was made.

`SUPABASE_ACCESS_TOKEN` is unset. Managed backup and point-in-time recovery were not verified. No `pg_dump` was taken in this pass.

## Chain

One linear head. No branch.

`20261104_0001` → `0002` → `20261105_0003` → `20261107_0004` → `20261108_0005` → `0006` → `0007` (applied) → `0008` → `0009` → `0010` → `0011` (head, not applied).

## Catalog before apply

Pending relations are absent: `news_alerts`, `news_alert_deliveries`, `news_alert_preferences`, `news_collection_lease`, `llm_evaluations`, `news_event_revisions`, `backtest_shadow_runs`, `llm_budget_ledger`.

Existing rows that must survive:

| Table | Rows |
| --- | --- |
| `app.news_events` | 10 |
| `app.news_articles` | 2 |
| `app.news_classifications` | 14 |
| `app.paper_sessions` | 3 |
| `app.paper_orders` | 0 |
| `app.paper_fills` | 0 |
| `app.signal_history` | 0 |
| `app.order_intents` | 0 |
| `app.order_executions` | 0 |

## SQL impact

Each upgrade runs in one Alembic transaction on PostgreSQL. A failure rolls that revision back. Earlier revisions stay. These files do not rewrite existing rows. They create new empty tables in schema `app`.

`0008` adds a foreign key from `news_alerts.event_id` to `app.news_events.event_id` with `ON DELETE CASCADE`. Creating that constraint takes a short lock on `news_events` while Postgres checks the current 10 event ids. It does not copy or update those rows. A later delete of an event would delete its alerts. Revisions in `0010` do not use that foreign key, so deleting the latest upsert cannot erase revision history.

No migration grants privileges to `anon` or `authenticated`. Each new table enables RLS and adds `{table}_select_own` for `SELECT` to `authenticated`, using `owner_user_id IS NULL OR owner_user_id = auth.uid()`. The privileged pooler role bypasses RLS. Application routes remain the write gate.

Downgrade drops only the objects that revision created. It would destroy rows later written into those new tables. It does not drop `news_events`, paper sessions, or signal tables. Do not downgrade automatically after a failed or unwanted apply.

### 0008 — alerts and lease

- Tables: `news_alerts`, `news_alert_deliveries`, `news_alert_preferences`, `news_collection_lease`.
- Alert idempotency: unique `idempotency_key`. Acknowledgement time is a nullable `acknowledged_at_ms` column. Status defaults to `OPEN`.
- Delivery idempotency: unique `idempotency_key`. `provider_message_id` and `confirmed_at_ms` stay null until a real provider confirms. The application must not invent a receipt.
- Delivery rows reference `news_alerts` with `ON DELETE CASCADE`.
- Preferences: `telegram_enabled` defaults false. Unique `owner_user_id` allows multiple SQL NULLs, so a global preference must use one stable `preference_id` in application code.
- Lease: primary key `lease_name`. The application upserts `news_collect` only when the existing lease is expired or already owned by the same worker. Two workers cannot both refresh a live lease.
- Indexes: alert status/severity by created time, and delivery by alert and channel.

### 0009 — LLM audit

- Table: `app.llm_evaluations`.
- Unique `idempotency_key`. No foreign key to signals, so a missing local signal id cannot block the migration.
- Stores model name, prompt template version, token counts, estimated cost, coordinator action, risk verdict, notional, agreement, and a reasoning summary capped by the repository at 2000 characters.
- `llm_changed_decision` defaults false.
- No column for an API key, prompt body, or article text. The repository persists the summary, not the provider credential.
- Index on symbol and requested time.

### 0010 — revisions and shadow runs

- `news_event_revisions`: unique `(event_id, revision_number)`. No foreign key to `news_events`.
- Availability columns are nullable. The migration does not fill them from `published_at_ms` and does not insert the existing 10 events.
- Trigger `news_event_revisions_no_mutation` calls `app.prevent_news_revision_mutation()` and rejects UPDATE and DELETE. `EXECUTE FUNCTION` matches Supabase Postgres 15.
- Index `ix_news_event_revisions_symbol_recorded` is only on `recorded_at_ms`. The name mentions symbol; symbol values live in `symbols_json`. This does not block apply.
- `backtest_shadow_runs` stores mode, hashes, provenance, and metrics. `llm_changed_decision` defaults false. It does not store an API key.
- Downgrade drops the trigger, function, policies, and both tables.

### 0011 — budget ledger

- Table: `app.llm_budget_ledger`.
- Unique `idempotency_key`. Index on `created_at_ms, status`.
- The migration does not install a lock. Cross-process safety is in `PostgresDurableBudget`, which takes `pg_advisory_xact_lock(hashtext('cryptonova_llm_budget'))` before counting and inserting.
- Hourly cap counts every ledger row in the last hour, including released calls.
- Daily cap sums committed `actual_usd` and still-reserved `reserved_usd`. Released rows contribute zero.
- A repeated idempotency key returns `reservation_pending` and does not call the provider again.
- A provider failure is released with `actual_usd` 0. A commit uses `max(min_call_usd, reported_usd)`, so an unknown or zero reported cost still consumes the reserved minimum.
- If the commit update fails, the row stays `reserved` and continues to count against the daily cap.
- If the table is missing or the transaction errors, `try_begin` returns `budget_storage_unavailable` and the service does not call the provider.
- SQLite is rejected.

## Revision writer, before any apply

The article upsert calls the archive writer inside a savepoint. A missing `0010` table, or any other database error on the archive insert, rolls back only that savepoint. The article transaction can still commit. The in-memory status becomes `archive_unavailable`.

`NewsService.status()` always returns `historical_provenance=incomplete`. It does not report a complete archive when the savepoint fails. There is no separate durable diagnostics row for that failure. The existing 10 events will remain without revisions after `0010`, because this writer does not backfill.

Concurrent inserts of the same `(event_id, revision_number)` are ignored by `ON CONFLICT DO NOTHING`. Two different material hashes for the same event append the next revision number only if each transaction sees the prior row. The unique pair prevents a duplicate number. A lost race can skip or collide; the collision is discarded rather than rewritten.

## Runtime impact of a future apply

Creating empty tables does not change trading decisions, paper fills, or the 10 existing news rows. Alerts, LLM audit, revision capture, and durable budget accounting stay inactive until the tables exist and the matching feature flags are turned on. Those flags stay off. The running API process was not restarted in this phase and still predates the new routes.

## Recovery if a future apply fails

1. Stop. Do not run `alembic downgrade`.
2. Read `app.alembic_version` and compare it with the last successful revision.
3. Because each upgrade is transactional, a failed revision should leave the version at the previous id and leave no partial table from that file.
4. Existing news, paper, and signal rows are outside these four downgrade paths.
5. A managed restore is not available as a verified recovery point. Do not start the apply until the operator accepts that, or takes a logical backup first.

## Exact approval still required

This preflight does not authorize `alembic upgrade`.

Approve applying CryptoNova migrations 0008 through 0011 to the verified development Supabase project only.
