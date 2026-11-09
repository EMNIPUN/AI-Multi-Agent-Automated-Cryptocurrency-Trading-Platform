# CryptoNova 76 — Dashboard and API Readiness

No login was bypassed. No privileged database connection was used as a stand-in for a user. A signed-in browser session was not available, so authenticated page behavior stays unverified.

## Routes

| Page | Frontend | API | Auth |
| --- | --- | --- | --- |
| `/agents` | `apps/web/src/app/agents/page.tsx` | Signals live under `/api/v1/signals`. The agents page itself is a static catalog. | Prefix is in `PROTECTED_ROUTE_PREFIXES`. `RequireAuth` is a UI gate. API JWT checks remain separate. |
| `/paper` | `apps/web/src/app/paper/page.tsx` | `/api/v1/paper` | Same UI gate. Read API is disabled by default and does not open the database while disabled. |
| `/analytics` | `apps/web/src/app/analytics/page.tsx` | `/api/v1/paper/sessions/{session_id}/analytics` and the trades, equity, and symbols subroutes | Same UI gate. |
| `/news` | `apps/web/src/app/news/page.tsx` | `/api/v1/news` | Same UI gate. GET does not ingest. |
| `/llm` | `apps/web/src/app/llm/page.tsx` | `/api/v1/llm` | Same UI gate. Runtime model calls stay off. |
| `/backtesting` | `apps/web/src/app/backtesting/page.tsx` | `/api/v1/backtests` | Same UI gate. |

## UI states present in code

| Page | Loading | Empty | Error |
| --- | --- | --- | --- |
| `/agents` | The catalog is static, so it has no remote loading state. The shell shows a session skeleton while `RequireAuth` is not ready. | Coming-soon card for the unimplemented SMC agent. | No remote error state on the static catalog. |
| `/paper` | Yes | Yes | Yes, including a sign-in presentation when unauthorized |
| `/analytics` | Yes | Yes | Yes, including `paper_db_missing` |
| `/news` | Yes | Yes | Yes |
| `/llm` | Yes | Yes | Yes |
| `/backtesting` | Yes | Yes | Yes, including unreachable and missing-directory modes |

Frontend tests cover paper, analytics, news, LLM, and backtest UI helpers. They use local fixtures, not the development database.

## Secrets

Client code uses the public Supabase URL and anon key. Server logs redact database URLs. This phase did not print tokens, connection strings, or the owner UUID.

## Unsigned HTTP check

After the production build, the development server was restarted. The first response for `/agents`, `/paper`, `/analytics`, `/news`, `/llm`, and `/backtesting` was HTTP 200 with no `Location` header. The paper document contained the session-check and sign-in text. That is the UI gate before hydration finishes a client redirect. It is not a signed-in session.

## Unverified

Signed-in dashboard data against the development API was not exercised. The API listener was not started, because signal-store startup can commit a risk row when the owner is configured and the source of truth is Postgres.
