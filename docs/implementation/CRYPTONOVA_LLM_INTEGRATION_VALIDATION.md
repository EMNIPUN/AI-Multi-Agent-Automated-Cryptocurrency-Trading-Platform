# CryptoNova — LLM Integration Validation

**Status: IMPLEMENTED BUT UNVERIFIED for a signed-in recommendation history. Budget status is live. No paid call was made.**

`NEWS_LLM_ENABLED` remains false. Live `GET /api/v1/llm/status` returned:

- `enabled=false`
- `provider_called=false`
- budget storage `postgres`
- `durable_across_processes=true`
- daily budget `1.0`
- calls this hour `0`

`app.llm_evaluations` and `app.llm_budget_ledger` exist and contain no application rows after test cleanup. The earlier isolated test covered reservation, hourly concurrency, restart idempotency, failed-call release at zero, unknown cost using the reserved minimum, the daily cap, and a dead database blocking the provider. Those used a mock transport.

The LLM page shows the advisory label, spend, remaining budget, and calls this hour from the status payload. A signed-in browser session was not available, so that layout was not clicked.

The model name is not configured. A key is present on the server. The browser proxy does not expose `POST /api/v1/llm/evaluate`. `llm_changed_decision` stays false.
