# CryptoNova — 70B Runtime Validation

**Status: API restarted and probed on 2026-11-08. Signed-in pages were not opened.**

The previous development API was `uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8200`. A close request did not stop the Windows worker, so that process tree was force-stopped and the same command was started again from this repository. Next.js on port 3000 was left running. Nothing is listening on port 8000.

Direct `127.0.0.1:8200` and the Next proxies:

| Route | Result |
| --- | --- |
| `/api/v1/news/status` | 200. Storage `supabase_postgres`, available, provenance `incomplete`, alerts/LLM/Telegram/auto-collection false |
| `/api/v1/llm/status` | 200. Enabled false, provider calls 0, audit storage available, `llm_changed_decision` false. A key is configured and no model name is configured |
| `/api/v1/backtests/shadow-status` | 200. `historical_news_backtest_valid` false. The payload still lists `0008`–`0011` as pending and the last verified revision as `0007`. That text is hardcoded and is behind the database |
| `/api/v1/paper/status` | 200. Read API disabled, no database opened, `execution_allowed` false, label `SIMULATED / PAPER ONLY` |
| `/api/v1/signals/status` | 500. `signal_cloud_owner_user_id_unset` because Supabase source-of-truth defaults on and no owner id is set |

Unsigned browser visits to `/news`, `/llm`, `/backtesting`, `/analytics`, `/paper`, and `/agents` render the page name and redirect to sign-in. `/news` reached `/login?next=/news`. Signed-in records, empty states, and console errors on those dashboards were not verified.
