# CryptoNova — 69D OpenAI LLM Intelligence

## Result

Optional, explainable decision support is implemented beside the deterministic pipeline. A model suggestion can be stored and compared. It cannot change the trade, the risk verdict, the position size, or an exchange order.

## Where it runs

`SignalPipeline.evaluate` still ends at Risk. `LlmDecisionSupportService.evaluate` is a later, explicit step. The HTTP entry is `POST /api/v1/llm/evaluate`, operator-local only. Market, Trend, Momentum, Coordinator, and Risk do not import the LLM package.

## Provider

`OpenAiProvider` uses the official `openai` SDK with structured JSON schema `69D.1.0`, the configured model only, and a timeout. Tests inject a scripted transport. Automated tests do not make paid calls.

## Storage

Alembic `20261108_0009` revises `20261108_0008` and creates `app.llm_evaluations` with select-own RLS. Neither `0008` nor `0009` is applied. The last read-only development check this session was revision `20261108_0007` on project `wmirifmgaftassgrfbyl`. This milestone did not run `alembic upgrade`.

Development apply, only after approval, and only after `0008`:

1. `CRYPTONOVA_DB_TARGET=development`
2. `CRYPTONOVA_DEV_PROJECT_REF=wmirifmgaftassgrfbyl`
3. `CRYPTONOVA_USE_DATABASE_URL_AS_DEV=true`
4. `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=yes` in that shell only
5. `uv run alembic -c apps/api/alembic.ini upgrade 20261108_0008`
6. Then `upgrade 20261108_0009`

Until that schema exists, runtime audit storage is unavailable and the service will not call OpenAI.

## API and dashboard

- `GET /api/v1/llm/status`
- `GET /api/v1/llm/evaluations`
- `GET /api/v1/llm/evaluations/{id}`
- `GET /api/v1/llm/comparisons`
- `GET /api/v1/llm/report`
- `POST /api/v1/llm/evaluate`

`/llm` shows **LLM Advisory Only — Trading Decisions Unchanged**, status, the comparison report, and stored rows when the API is reachable. It does not render demo evaluations and does not show an LLM line as a profitable signal. The signed-in page was not opened in a browser.

## Tests

```
uv run pytest tests/test_core_llm_69d.py tests/test_core_news_69a.py tests/test_core_news_69a1.py tests/test_core_news_69b.py tests/test_core_news_69c.py tests/test_phase4a_multi_agent_signals.py tests/test_core_paper_broker.py tests/test_core_backtest_68a.py -q
→ 107 passed, 1 skipped, 0 failed
```

The skip is the optional live Postgres news integration. Web `llm-format.test.ts`: 2 passed. Web `news-format.test.ts`: 4 passed.

## Safety

`NEWS_LLM_ENABLED` and `AGENT_ALLOW_LIVE` stay false. `llm_changed_decision` is false. No live orders, no production migration, and no automatic OpenAI spend.
