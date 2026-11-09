# CryptoNova — Security Audit

**Status: IMPLEMENTED BUT UNVERIFIED as a full least-privilege cutover.**

## Confirmed

- Development identity guard matches project `wmirifmgaftassgrfbyl` only.
- `.env` keeps `CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false` and `AGENT_ALLOW_LIVE=false`.
- News LLM, advisory, alerts, Telegram, and automatic collection default off.
- New tables have select-own RLS for `authenticated` and no `anon` grants.
- The API role in `DATABASE_URL` is the privileged `postgres` role. It bypasses RLS. Application routes are the write gate.
- LLM evaluate is not proxied to the browser. GET status does not call the model.
- Operator news, LLM, and backtest routes reject a forwarded client address.
- News text stays untrusted. Sentiment is not a trade.
- Revision rows reject UPDATE and DELETE.

## Open

- A runtime role that does not bypass RLS is not in use for these routes.
- `ensure_offline_sot()` can turn source-of-truth mode off inside the API process when a backtest journal opens.
- Signal reads fail closed without an owner id. That is safer than an unbound cloud write, and it is not a completed owner-scoped API.
- Signed-in authorization on the dashboards was not exercised.
- An earlier failed backup attempt put a database connection string in a local tool log. Rotate that development password when convenient. It is not repeated here.

No production credential was selected. No live order was sent.
