# Phase 3 — CryptoNova Command Center

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Project | CryptoNova — Intelligent Trading. Disciplined Execution. |
| Scope | Audit + incremental UI (notifications). Live trading stays off. |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Migration `20261104_0002` | **Not applied** (not inspected remotely; not executed) |
| Live Bybit order HTTP | **Disabled** |
| Live private SSE | **Disabled** (`403`) |
| Paper order submit | **Disabled** |

This report records the repository as it exists after Phase 3A premium frontend plus this increment. It does not claim live agent telemetry, owned positions, or a persistent paper broker.

---

## Repository audit

| Area | Finding |
|------|---------|
| Frontend | Next.js 15.1.3 App Router, TypeScript, Tailwind, shadcn/ui, Magic UI patterns, React Flow, Lightweight Charts, Recharts |
| Routes already present | `/dashboard`, `/agents`, `/agents/live`, `/markets`, `/portfolio`, `/positions`, `/paper`, `/risk`, `/analytics`, `/settings` |
| Added this increment | `/notifications` |
| Bybit wallet | `GET /api/v1/exchange/wallet` → Next proxy `/api/exchange/wallet`. Server-side keys only. UNIFIED account fields kept distinct. Gated by `EXCHANGE_WALLET_READS_ENABLED`. **Preserved.** |
| Wallet ownership | Operator-local keys on the API process. Not a per-user exchange binding. Do not treat any logged-in browser user as authorized for that account. |
| Observability | Fixture snapshots when `OBSERVABILITY_FIXTURE_MODE=true`. Live snapshot returns 503. SSE requires auth and still returns 403 until private reads + live stream flags. |
| Risk / positions pages | Honest unavailable placeholders. No invented halt or exposure. |
| Paper | SAMPLE workspace. Submit disabled. No Bybit `create_order`. |
| Local SQLite | Still the execution/fill/risk source of truth. UI does not write it. |
| Alembic `0002` | Not applied in this session. No remote DDL. |

---

## Features implemented (cumulative)

- Premium dark shell, sidebar, CryptoNova mark (transparent emblem), shadcn spinner + Magic UI ripple loaders.
- Dashboard with wallet panel (live UNIFIED read when the API flag is on) and SAMPLE agent cards.
- Agent Command Center: status, heartbeat stale flag, symbol/timeframe, EMA/RSI, signal, risk verdict, order lifecycle, event timeline, React Flow, candlestick chart. SAMPLE labeled. ACCEPTED is not shown as FILLED.
- Markets, portfolio, analytics, settings shells.
- Notifications center: snapshot events filtered to error/halt/blocked/reconciliation types, deduped by `event_id`, local time plus UTC.

## Not implemented (blocked on purpose)

- Live agent heartbeat from the worker (publisher remains null).
- Authenticated private SSE fan-out.
- Bybit positions, open orders, and fill-history read adapters.
- Durable risk snapshot API (HALTED stays in the engine, not the browser).
- Persistent paper ledger, fees, slippage, idempotent fills.
- Web controls that place, cancel, or close real orders.
- Automatic enable of `PRIVATE_DATA_READS_ENABLED` or migration `0002`.

---

## Live vs fixture matrix

| Surface | Mode |
|---------|------|
| UNIFIED wallet | Live read-only when exchange wallet reads are enabled; otherwise unavailable |
| Agent command center | SAMPLE fixture (or local fixture if API is down) |
| Workflow nodes | Driven by fixture pipeline state, labeled DEMO |
| Positions / risk | Unavailable — empty, not invented |
| Paper balances and orders | SAMPLE; submit disabled |
| Analytics curve | SAMPLE |
| Notifications | Derived from the same SAMPLE snapshot |
| SSE | Disabled |

---

## Event streaming

Envelope and event names live in `apps/api/app/observability/types.py` and the web mirror under `apps/web/src/lib/observability`.

`GET /api/v1/observability/stream` requires a principal and returns **403** `observability_live_stream_disabled` while private reads are off. Tokens are not accepted in the query string. There is no shared unauthenticated stream.

---

## Security non-actions

- No migration apply
- No private-read flag change
- No live order, leverage, cancel, or close routes
- No secrets in the client
- No git commit or push

---

## Tests

Prior Phase 3A run (unchanged code paths except notifications UI):

- `apps/web`: typecheck pass, event script pass, production build pass (SWC Win32 warning, fallback succeeded)
- `uv run pytest -q`: 178 passed

This increment adds a page and a nav item only. Notifications were not given a new automated test in this pass. Re-run `npm run typecheck` and `npm run build` in `apps/web` before treating the route as release-ready on this machine.

---

## Recommended next milestone (Phase 3B)

1. Bind each operator to one exchange account before any positions/orders read.
2. Emit worker observability events with stable `event_id`s; then enable owner-scoped snapshot (still no trading).
3. Read-only positions and open orders behind that binding, with Bybit timestamps and stale banners.
4. Persistent paper broker in a separate store, then enable submit.
5. Only after ownership migration is verified: consider private SSE. Do not apply `20261104_0002` until that review is explicit.
