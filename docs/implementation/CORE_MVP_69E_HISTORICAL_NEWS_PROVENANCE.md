# CryptoNova — 69E Historical News Provenance

## What the database can prove

`app.news_events` stores the latest upsert of an event. A later edit replaces severity, sentiment, verification, and classification time. That row cannot be rewound.

Development was last read at Alembic `20261108_0007`. These revisions are written and not applied:

| Revision | Contents |
| --- | --- |
| `20261108_0008` | Alert tables |
| `20261108_0009` | LLM audit table |
| `20261108_0010` | Append-only `app.news_event_revisions` and `app.backtest_shadow_runs` |

`0010` revises `0009`. It enables select-own row-level security, does not foreign-key history to the mutable event row, and installs a trigger that rejects UPDATE and DELETE.

No backfill was invented. Existing events have no reliable revision chain, so they are marked incomplete.

## Point-in-time rule

`build_historical_news_context(symbol, as_of_time, revisions)` keeps a revision only when all of these are true:

- `first_available_at_ms <= as_of_time`
- `revision_available_at_ms <= as_of_time`
- `recorded_at_ms <= as_of_time`
- publication time, when present, is also `<= as_of_time`

An article whose publication date is old, but whose archive row was recorded later, is excluded. That is a backfill, not knowledge the system had at `as_of_time`.

The newest visible revision number for an event is the one used. A future revision is ignored. Another symbol is ignored. A row missing first-available, revision-available, or recorded time is incomplete and is not reconstructed from the current event.

`refuse_latest_row_as_history` returns no events.

## Validity

Historical news backtesting on the development database is **not valid**. A fixture can set `archive_complete=True` only for that supplied revision list. The shadow status endpoint reports `historical_news_backtest_valid: false`.

## Apply plan, after explicit approval, development project `wmirifmgaftassgrfbyl` only

1. `CRYPTONOVA_DB_TARGET=development`
2. `CRYPTONOVA_DEV_PROJECT_REF=wmirifmgaftassgrfbyl`
3. `CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true`
4. `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` in that shell only
5. Upgrade `20261108_0008`, then `20261108_0009`, then `20261108_0010`

Do not apply these to production. Until `0010` is applied, runtime archive storage stays unavailable. Tests do not fall back to a silent in-memory source of truth.
