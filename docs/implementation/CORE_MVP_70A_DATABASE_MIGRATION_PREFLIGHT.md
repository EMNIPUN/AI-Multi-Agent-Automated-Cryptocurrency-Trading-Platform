# CryptoNova — 70A Database Migration Preflight

Read-only check on 2026-11-08. Identity guard accepted development project `wmirifmgaftassgrfbyl` on `aws-0-ap-southeast-2.pooler.supabase.com` (session pooler). Alembic current is **`20261108_0007`**. No upgrade was run. Credentials were not printed.

## Chain

`0001` → `0002` → `0003` → `0004` → `0005` → `0006` → `0007` (applied) → `0008` → `0009` → `0010` → `0011` (all four pending, linear).

Each file sets `down_revision` to the previous id. There is no branch.

## 0008 — alerts

Creates `news_alerts`, `news_alert_deliveries`, `news_alert_preferences`, `news_collection_lease`.

- Foreign key: `news_alerts.event_id` → `app.news_events.event_id` ON DELETE CASCADE. `news_events` already exists at `0007`.
- Unique idempotency keys on alerts and deliveries.
- Indexes on status/severity and delivery channel.
- RLS: `{table}_select_own` for `authenticated`, `owner_user_id IS NULL OR owner_user_id = auth.uid()`.
- No GRANT of schema usage to `anon`.
- Empty tables. No backfill. Rollback drops policies then tables.

Lock risk is short `CREATE TABLE` on an empty relation. The cascade means deleting an event later deletes its alerts. That is acceptable for alerts, and it is why `0010` does **not** use the same foreign key for revisions.

## 0009 — LLM audit

Creates `app.llm_evaluations`. No foreign key to signals or news, so a missing decision id cannot block the migration. Unique `idempotency_key`. Index on symbol and requested time. `llm_changed_decision` defaults false. Same select-own RLS. Rollback drops the policy and table.

## 0010 — revisions and shadow runs

Creates `news_event_revisions` and `backtest_shadow_runs`.

- No foreign key to `news_events`, so deleting the latest upsert cannot erase history.
- Unique `(event_id, revision_number)`.
- Trigger `news_event_revisions_no_mutation` calls `app.prevent_news_revision_mutation()` and rejects UPDATE and DELETE.
- Requires PostgreSQL `EXECUTE FUNCTION` (Supabase Postgres 15).
- Same select-own RLS on both tables.
- Does not copy existing `news_events` rows. Events stored before this migration stay without revisions.

## 0011 — budget ledger

Creates `app.llm_budget_ledger` after `0010`. Unique idempotency key. Index on created time and status. Select-own RLS. No seed rows. Runtime code fail-closes until this table exists.

## Privileged role

`DATABASE_URL` bypasses RLS. API gates remain the application control. Do not grant these tables to `anon`.

## Apply order, only after a separate explicit approval

1. `CRYPTONOVA_DB_TARGET=development`
2. `CRYPTONOVA_DEV_PROJECT_REF=wmirifmgaftassgrfbyl`
3. `CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true`
4. `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` in that shell only
5. `uv run alembic -c apps/api/alembic.ini current` and confirm `20261108_0007`
6. Upgrade `0008`, then `0009`, then `0010`, then `0011`
7. Confirm `current` is `20261108_0011`
8. Leave the `.env` approval flag false afterward

Do not apply to production. Do not enable `NEWS_ALERTS_ENABLED`, `NEWS_LLM_ENABLED`, or `NEWS_AUTO_COLLECTION_ENABLED` until the matching table exists.

## Prerequisite fixes

No schema rewrite is required before that approved apply. The archive writer and budget ledger already no-op or fail closed while the tables are absent, so applying the migrations does not depend on a code change landing later. Old news still will not become historically complete.
