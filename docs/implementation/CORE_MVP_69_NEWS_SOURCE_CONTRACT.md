# News Source Contract (69A)

## Providers

| Provider | ID | Delayed? | Access |
| --- | --- | --- | --- |
| Fixture (offline) | `fixture_offline` | No | Always (tests/demo) |
| Public RSS | `rss_public` | **Yes** (default) | `NEWS_RSS_FEED_URLS` |
| NewsData.io | `newsdata_io` | **Yes** on typical free plans | `NEWSDATA_API_KEY` |

Delayed feeds must set `is_delayed_feed=true` and never be advertised as immediate critical detection.

## Validation

- HTTPS/HTTP URLs only
- Title length ≥ 8
- Reject future `published_at`
- Prompt-injection markers detected and truncated from excerpts
- Content hash = SHA-256(`title|url|published_at_ms`)

## Timestamps (UTC ms)

| Field | Meaning |
| --- | --- |
| `published_at_ms` | Publisher claim |
| `first_observed_at_ms` | Provider observation |
| `ingested_at_ms` | CryptoNova ingest |
| `available_at_ms` | Classification available (max of observed/ingested) |

Context snapshots never include events with `available_at_ms > as_of`.
