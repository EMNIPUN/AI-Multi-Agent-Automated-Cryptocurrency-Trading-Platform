# CryptoNova 72 — Dashboard Integration

No signed-in session was available. Authentication was not bypassed. Signed-in balances, news rows, LLM recommendations, and backtest results were not verified in the browser.

Unsigned navigation on `http://127.0.0.1:3000` after the development server was restarted:

| Route | Observed page | Then |
| --- | --- | --- |
| `/agents` | Agents, "Redirecting to sign in…" | `/login?next=/agents` |
| `/paper` | Demo Trading, "Redirecting to sign in…" | same sign-in gate |
| `/analytics` | Analytics, "Redirecting to sign in…" | same sign-in gate |
| `/news` | News, "Redirecting to sign in…" | same sign-in gate |
| `/llm` | LLM Intelligence, "Redirecting to sign in…" | same sign-in gate |
| `/backtesting` | Backtesting, "Redirecting to sign in…" | `/login?next=/backtesting` |

The login document did not contain a Postgres URL. The only `sk-` match was a 12-character lowercase stylesheet token, not an API key.

`next build` succeeded, including those six routes. `tsc --noEmit` succeeded after the news dashboard stopped casting alert rows to `never[]`.

A production build briefly broke the running Turbopack dev server. `npm run dev` was restarted and the unsigned pages rendered again.

API connectivity from the same machine, without a browser session:

- signals status 409 `signal_owner_unconfigured`
- paper status 200, read API false
- LLM status 200, enabled false, provider not called
- shadow status 200, revision `20261108_0011`, historical news backtest invalid
- news status 200, provenance incomplete
