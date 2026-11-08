# News Alert API Contract (69B)

Base path: `/api/v1/news`  
Auth: existing operator loopback gate (`require_news_local_access`). Read routes also require `NEWS_READ_API_ENABLED=true`.

GET routes do not collect news and do not send Telegram messages.

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/alerts` | Page of stored alerts. `enabled:false` and empty items when `NEWS_ALERTS_ENABLED` is false. Query: `limit` (1–100), `offset`, `severity`, `symbol`, `status`. |
| GET | `/alerts/unread-count` | Open-alert count. `unread:0` when the engine is disabled. |
| GET | `/alerts/{alert_id}` | Alert plus in-app/Telegram delivery rows. `alert_id` must match `nal_*`. |
| POST | `/alerts/{alert_id}/acknowledge` | Sets `ACKNOWLEDGED` and `acknowledged_at_ms`. Requires alerts enabled. Idempotent. |
| GET | `/alert-settings` | Stored preferences or defaults. |
| PUT | `/alert-settings` | Updates min severity, symbols (max 20), cooldown (1 min–24 h), ttl (1 min–7 d), in-app and Telegram preference flags. |

Each alert includes `agent_context` for a future 69C reader:

- `event_id`, `symbol` / `symbols`, `severity`, `verification`
- `first_available_at_ms`, `freshness`
- `source_evidence`, `warnings`
- `advisory_only: true`, `places_orders: false`

Storage missing (`20261108_0008` not applied) returns HTTP 503 `alerts_schema_unavailable` when the engine is enabled. Disabled engine does not pretend there are alerts.

Next.js same-origin proxies live under `apps/web/src/app/api/news/alerts/**` and `alert-settings`.
