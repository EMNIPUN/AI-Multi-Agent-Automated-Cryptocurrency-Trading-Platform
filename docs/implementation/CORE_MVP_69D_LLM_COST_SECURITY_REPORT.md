# CryptoNova — 69D Cost and Security

## Defaults

`NEWS_LLM_ENABLED` is false. `AGENT_ALLOW_LIVE` is false. Empty `OPENAI_API_KEY` and `CRYPTONOVA_LLM_MODEL` return `missing_api_key` or `missing_model` and do not construct a paid request.

Suggested limits, not a billing guarantee:

- timeout 20 seconds
- 20 calls per hour
- USD 1.00 estimated daily budget
- concurrency 2
- at most two retries, and only after a provider rate limit

Cost is a conservative estimate (`min` USD 0.01 per accepted call, plus a high per-token ceiling). It is not an OpenAI invoice. The budget is there to stop early, not to predict the bill.

## Secrets

The API key stays in server settings. Status responses expose `api_key_configured` only. Article text is untrusted, length-limited, and stripped of key-shaped strings before it is placed in the user message. The system message is a fixed instruction and does not contain article text. News cannot grant tools or change permissions.

The Next.js proxy allows GET status, evaluations, comparisons, and report. It does not proxy `POST /api/v1/llm/evaluate`, so the browser cannot start a paid call. GET handlers do not call the model.

## Database

`DATABASE_URL` is the privileged server role and bypasses row-level security, as with the news tables. Authenticated select policy `llm_evaluations_select_own` is in migration `20261108_0009` and is not applied. No account identifiers or credentials are columns on the audit row.

If `app.llm_evaluations` is missing, the service returns `storage_unavailable` and does not call the provider. In-memory storage is test-only.

## Historical news

`app.news_events` keeps the latest upsert, not revision history. The LLM input always records `revision_history_available=false` and the warning `revision_snapshots_unavailable`. The builder does not invent an earlier classification.
