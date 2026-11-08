# Agent Context Contract (prepared in 69A, wired in 69C)

## NewsContext schema version `1.0.0`

Built by `agent/news/context_provider.py`.

Fields: `symbol`, `as_of`, `events[]`, `context_status`, `schema_version`, `warnings`.

`context_status`: `AVAILABLE | STALE | UNAVAILABLE | UNVERIFIED | ERROR`

## 69A behavior

- Context can be fetched via `GET /api/v1/news/context/{symbol}`.
- **Not** injected into `SignalPipeline.evaluate` / `coordinate`.
- `NEWS_AGENT_ADVISORY_ENABLED` remains false; no BUY/SELL/HOLD changes.

## 69C

Implemented. See `CORE_MVP_69C_NEWS_CONTEXT_CONTRACT.md`. Advisory attachment does not change BUY/SELL/HOLD, risk vetoes, or size. `news_changed_decision` is false.
