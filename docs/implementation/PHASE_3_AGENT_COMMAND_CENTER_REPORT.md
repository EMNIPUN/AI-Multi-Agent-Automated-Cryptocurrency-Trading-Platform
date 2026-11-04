# Phase 3A — Agent Command Center

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova |
| Scope | Next.js Command Center + observability contracts (fixture mode) |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Migration `20261104_0002` | **Not applied** |
| Live Bybit / trading HTTP | **Disabled** |
| Live private SSE | **Disabled** |

---

## Created / modified files

### Frontend (`apps/web`)
| Path | Role |
|------|------|
| `package.json`, `tsconfig.json`, `next.config.ts`, `vitest.config.ts` | Next.js 15 + Vitest scaffold |
| `src/app/layout.tsx`, `globals.css`, `page.tsx` | Shell + overview |
| `src/app/agents/live/page.tsx` | Agent Command Center |
| `src/app/paper/page.tsx` | Paper workspace |
| `src/app/api/observability/*` | Same-origin snapshot/paper/stream proxy |
| `src/components/*` | Status, pipeline, chart, timeline, orders, paper |
| `src/lib/observability/*` | Typed contracts + dedupe/reconnect helpers + tests |
| `src/lib/fixtures/agentSnapshot.ts` | Bundled SAMPLE fallback |
| `README.md` | Operator notes |

### Backend
| Path | Role |
|------|------|
| `apps/api/app/observability/types.py` | Event + snapshot schemas (`schema_version` 1.0.0) |
| `apps/api/app/observability/fixtures.py` | Labeled SAMPLE agent + paper snapshots |
| `apps/api/app/observability/store.py` | Idempotent in-memory buffer + cursor |
| `apps/api/app/observability/publisher.py` | Null / in-memory publisher |
| `apps/api/app/observability/router.py` | Read-only HTTP contracts |
| `apps/api/app/config.py` | `OBSERVABILITY_*` flags; version `0.3.0-phase3a` |
| `apps/api/app/factory.py` | Mount observability router |
| `agent/observability_publisher.py` | Runner hook re-exports (default null) |
| `apps/worker/EVENT_PUBLISHER_PLAN.md` | Worker emission + reconnect plan |
| `tests/test_observability_phase3a.py` | Fixture/auth/stream negative tests |
| `.env.example` | Observability flag placeholders |

---

## Dashboard layout

### `/agents/live`
- Agent status badge: RUNNING / IDLE / OFFLINE / HALTED / UNKNOWN
- Heartbeat + **STALE** warning
- Symbol / interval, execution mode, paper vs real-readonly money view
- Last confirmed candle timestamp
- EMA/RSI + signal + risk verdict (from fixture when SAMPLE)
- Pipeline visualization with BLOCKED/HALTED highlighting
- Lightweight Charts candlesticks + SAMPLE markers
- Order lifecycle table + event timeline with correlation IDs
- Explicit SAMPLE banner; no fake RUNNING animation while offline

### `/paper`
- Virtual equity, cash, PnL, positions (SL/TP), simulated order history
- Submit control **disabled**; `broker_implemented=false`

Screenshots: capture locally after `npm run dev` (browser optional). This phase does not embed binary screenshots in-repo.

---

## API and event schemas

Event types: `agent.heartbeat`, `market.candle_confirmed`, `analysis.completed`, `signal.generated`, `risk.approved`, `risk.blocked`, `order.intent_created`, `order.accepted`, `order.partially_filled`, `order.filled`, `order.canceled`, `order.reconciliation_required`, `agent.halted`, `agent.error`.

Envelope fields: `schema_version`, `event_id`, `correlation_id`, `occurred_at` (UTC), `env_scope`, optional `account_scope_label` (never raw fingerprint), optional `owner_user_id`, safe `payload`.

| Endpoint | Auth | Behavior (Phase 3A) |
|----------|------|---------------------|
| `GET /api/v1/observability/status` | none | Fixture/live flags |
| `GET /api/v1/observability/snapshot` | none (fixture) | SAMPLE `AgentSnapshot` |
| `GET /api/v1/observability/paper/snapshot` | none (fixture) | SAMPLE paper workspace |
| `GET /api/v1/observability/stream` | Bearer required | **403** `observability_live_stream_disabled` |

Browser uses same-origin Next proxy (`/api/observability/*`) so JWTs are never placed in SSE query strings.

---

## Real vs fixture boundaries

| Mode | When | UI labeling |
|------|------|-------------|
| `fixture` | Default (`OBSERVABILITY_FIXTURE_MODE=true`) | **SAMPLE** banner + chart tag |
| `live` | Not available until ownership + flags | Would omit SAMPLE |
| `unavailable` | Fixture off & private reads off | HTTP 503 |

Worker offline ⇒ fixture shows IDLE/OFFLINE + stale heartbeat + BLOCKED pipeline — **not** animated fake RUNNING activity.

---

## Worker heartbeat / event delivery plan

See `apps/worker/EVENT_PUBLISHER_PLAN.md`.

- Default publisher: **null** (no side effects on AgentRunner).
- Future: emit append-only events with idempotent `event_id`; never mutate SQLite SoT for UI.
- Reconnect: snapshot → cursor catch-up → client dedupe (`mergeSnapshotAndCursor`).

---

## Authentication / ownership limitations

- Private catalog reads remain gated (`PRIVATE_DATA_READS_ENABLED=false`).
- Live SSE requires auth **and** live+private flags; still not wired to a fan-out bus.
- Fixture snapshots are intentionally public SAMPLE data (no tenant secrets).
- Cross-tenant live streams are **not** enabled; do not treat fixtures as user-private.

---

## Paper trading gaps

- No persistent Python paper broker.
- Submit controls disabled.
- SAMPLE positions/orders only; never sent to Bybit.

---

## Tests and verification

### Python (actual)
```text
uv run pytest -q
174 passed, 1 warning
```

Coverage includes: labeled fixtures, stream 401/403, buffer dedupe/cursor, fixture-off fail-closed, no trading routes on observability router, prior Phase 1–2 regressions.

### Frontend (actual)
```text
node apps/web/scripts/check-events.mjs
check-events.mjs: ok
```

Event ordering / dedupe / reconnect / heartbeat-staleness logic verified with a dependency-free Node script.

`npm install` / `typecheck` / `build` **did not complete in this agent environment** (npm hung with no progress after several minutes; installs were killed). Operator should run locally:

```text
cd apps/web
npm install
npm run test
npm run typecheck
npm run build
```

### Explicit non-actions
- No Bybit network calls from tests
- No remote Supabase DDL
- No migration apply
- No flag flip for private reads / live SSE

---

## Remaining blockers

1. Operator apply + verify `20261104_0002` before any live private observability.
2. Wire AgentRunner → publisher at tick boundaries (null today).
3. Implement authenticated SSE fan-out + ownership filters.
4. Implement persistent paper broker before enabling submit UI.
5. Complete `apps/web` `npm install` + typecheck + build locally (blocked here by hung npm).
6. Optional browser screenshots for docs.

---

## Next integration steps

1. Approve/apply ownership migration (Phase 2E procedure).
2. Emit heartbeats from worker with stale thresholds matching UI.
3. Proxy live SSE through Next with server-side Authorization.
4. Replace fixtures gradually with owned snapshots — keep SAMPLE labeling until evidence is real.
5. Phase 3B+: paper broker + multi-agent coordinator UI (still no browser execution authority).

---

## Success checklist

| Criterion | Status |
|-----------|--------|
| Professional `/agents/live` Command Center | Implemented (fixture mode) |
| Pipeline + timeline + chart with SAMPLE labels | Implemented |
| Observability schemas + fixture API | Implemented |
| Live private data / execution disabled | Pass |
| Paper page without submit-to-exchange | Pass |
| Worker publisher plan + null adapter | Pass |
| Tests | See verification section (honest outcomes) |
