# NewsContext Contract (69C)

Schema version: `69C.1.0`  
Builder: `build_news_context(repo, symbol=..., as_of_ms=... | as_of_time=...)`

The snapshot is immutable. Sentiment is descriptive. It is never a BUY or SELL.

## Snapshot fields

`symbol`, `evaluation_time_utc`, `context_generated_at_utc`, `source_event_ids`, `events[]`, `context_status`, `freshness`, `delayed_provider`, `corroboration_status`, `warnings`, `data_completeness`, `storage_availability`, `schema_version`, `context_hash`, `revision_history_available`.

Each event includes category, severity, sentiment, verification, publication time, first observed time, first available time, source references, and delay/uncertainty warnings.

## Point-in-time rules

- Include an event only when `available_at_ms <= as_of` and `classification_at_ms <= as_of`.
- Publication time alone does not make an event visible.
- Invalid timestamps return `context_status=ERROR` and do not raise into the signal pipeline.
- Ordering is `(available_at_ms, event_id)`. Duplicate event ids keep the earliest available row in the returned page.
- Count is bounded by `max_events_per_context`.

## Schema gap

`app.news_events` stores the latest upsert, not a revision history. `revision_history_available` is false. A later classification cannot be unwound into the earlier text. The builder excludes a row whose classification timestamp is after `as_of` rather than inventing the prior version. `revision_snapshots_unavailable` is always reported.

## Advisory attachment

`NEWS_AGENT_ADVISORY_ENABLED` stays false. The pipeline consults news only when `news_advisory_enabled=True` is passed explicitly. `news_changed_decision` is false. There is no LLM recommendation.
