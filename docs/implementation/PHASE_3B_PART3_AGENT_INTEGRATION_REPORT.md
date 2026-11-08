# Phase 3B Part 3 — Agent Studio end-to-end integration

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Route | `/agents/live` |
| Scope | Offline E2E evidence path, operator-local auth, strategy explainability, chart correlation, UX polish |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Migration `20261104_0002` | **Not applied** |
| Live SSE | **Disabled** |
| Real order HTTP / Bybit mutations | **Not added** |
| Secrets | **Not printed** |
| Git commit / push | **Not performed** |

---

## 1. Existing implementation audit

### Real (application code)

| Layer | Status |
|-------|--------|
| Advanced Agent Studio UI (`features/agent-studio`) | Implemented — React Flow workflow, Decision Inspector, timeline, replay, LIVE/SAMPLE separation |
| `TelemetryLedger` + runner `_observe` | Implemented — durable SQLite event ledger; telemetry failures never change trade logic |
| Order lifecycle observer | Implemented — read-only intent/execution projection (`ACCEPTED ≠ FILLED`) |
| EMA/RSI strategy + evidence payload | Implemented — `explanation_code`, condition PASS/FAIL/NOT_EVALUATED, thresholds |
| Candle `recent_bars` in `market.candle_confirmed` | Implemented — chart series from recorded confirmed bars only |
| Signal markers (verified open-time only) | Implemented — orphan timestamps skipped when bars exist |
| Operator-local diagnostic gate | Implemented — TCP peer + loopback bind; rejects Authorization and forwarded headers |
| Next.js same-origin snapshot proxy | Implemented — LIVE never silently falls back to SAMPLE |

### Scaffolded / deferred

| Item | Status |
|------|--------|
| Per-user exchange ownership binding | Missing — migration `0002` not applied |
| Browser JWT access to worker telemetry / wallet | Fail-closed by design |
| Live SSE stream | Disabled until ownership validated |
| `PRIVATE_DATA_READS_ENABLED` | Remains false |
| Mainnet / live order HTTP | Remains disabled |

---

## 2. Real implementation vs fixture coverage

| Path | Coverage |
|------|----------|
| Runner → ledger → FastAPI `worker-snapshot` | **Real code**, offline mocked market/position (pytest) |
| Strategy evidence fields | **Real** `evidence_payload` / `ema_rsi` evaluation codes |
| Chart candles/markers | **Real** projection from ledger events; SAMPLE fixtures remain separate |
| Wallet balances | Operator-local Bybit read path only; browser JWT denied |
| Studio SAMPLE mode | Explicit fixture path only |
| Studio LIVE mode | Worker proxy; unavailable on auth/network failure (no SAMPLE mix) |

---

## 3. Local end-to-end integration evidence

Deterministic offline test: `tests/test_agent_integration_phase3b.py`

Verified scenarios (no exchange contact):

- Confirmed candle + `recent_bars` projection into snapshot candles
- EMA/RSI analysis + HOLD signal with `HOLD_NO_CROSS` / conditions
- BUY proposal blocked by UNKNOWN position → `risk.blocked` (no `plan_trade` / `execute`)
- Stale heartbeat → `OFFLINE` + `heartbeat_stale`
- Empty ledger via API → `data_mode=unavailable`
- Telemetry `safe_record` failure does not break `tick()`
- Markers require verified candle open time (orphan SELL skipped)
- Operator JWT + `X-Forwarded-For` denied for worker-snapshot and wallet

---

## 4. Security and ownership results

Shared gate: `apps/api/app/security/operator_local.py`

| Check | Behavior |
|-------|----------|
| `Authorization` present | **403** `operator_diagnostic_not_bound_to_user` |
| `X-Forwarded-For` / `X-Real-Ip` | **403** `operator_diagnostic_proxy_forward_rejected` |
| `API_HOST` not loopback | **403** `operator_diagnostic_bind_not_loopback` |
| TCP peer not loopback / testclient | **403** `operator_diagnostic_loopback_only` |
| Host header alone | **Not trusted** as auth |

Applied to:

- `GET /api/v1/observability/worker-snapshot`
- `GET /api/v1/exchange/wallet`

### Prerequisites for secure live browser telemetry (future)

1. Apply ownership migration `20261104_0002` (or equivalent) with verified user↔exchange binding.
2. Prove RLS / ownership before enabling `PRIVATE_DATA_READS_ENABLED`.
3. Replace operator-local credential wallet with per-user bound accounts.
4. Only then consider authenticated browser reads / SSE — still fail closed without binding.

Until then, browser LIVE remains fail-closed / unavailable when the Next.js server cannot reach loopback diagnostics as the operator process.

---

## 5. Strategy explainability fields

Emitted when the strategy genuinely evaluates (never fabricated):

| Field | Source |
|-------|--------|
| `strategy_id` / `strategy_version` | Signal / evidence payload |
| `explanation_code` | Deterministic codes (`HOLD_NO_CROSS`, `BUY_EMA_CROSS_UP_RSI_OK`, …) |
| Indicator values | `ema_fast`, `ema_slow`, `rsi` |
| Thresholds / periods | Settings mirrored into evidence |
| `conditions[]` | `{id, result}` PASS / FAIL / NOT_EVALUATED / UNKNOWN |
| Candle times | `candle_start_ms`, `candle_close_ms` |

Decision Inspector renders these fields; missing bits show **Evidence unavailable**. Trading decisions and risk rules were not changed.

---

## 6. Chart / signal correlation status

| Behavior | Status |
|----------|--------|
| Candles from recorded `recent_bars` | Done |
| Markers only when `candle_start_ms` matches a known bar open | Done |
| Event → chart focus (`show on chart`) | Done |
| Missing candles / empty series empty-state | Done |
| Lightweight Charts attribution | Preserved |
| Invented fills / execution prices | Not added |

---

## 7. UX improvements (premium Studio preserved)

- Why This Decision: strategy identity, conditions, thresholds, freshness
- Evidence freshness labels (fresh / stale / unavailable)
- Event-to-chart navigation
- Replay chronological gap warnings
- Accessible loading / empty / disconnected messaging
- Mobile tabs retained; reduced-motion respected via Motion
- LIVE / SAMPLE / REPLAY remain distinctly labeled — no fake workflow animation

---

## 8. Order state accuracy

Order lifecycle remains evidence-only from the intent store observer:

- Risk approval ≠ placement
- ACCEPTED ≠ FILLED
- Partial fills, cancels, UNKNOWN, RECONCILIATION_REQUIRED preserved
- Missing evidence → unavailable in UI tables / inspector

---

## 9. Test and build outputs

| Command | Result |
|---------|--------|
| `uv run pytest -q` | **212 passed** |
| `apps/web npm run typecheck` | **pass** |
| `apps/web npm run lint` | **pass** (SWC native binary warning on this host only) |
| `apps/web npm run test:events` | **ok** |
| `npx vitest run src/features/agent-studio` | **9 passed** |
| `apps/web npm run build` | **pass** |

Added / extended coverage:

- End-to-end mocked telemetry delivery
- Owner/JWT and proxy authorization denials
- HOLD explanation codes
- Event/chart time alignment
- Replay gap detection
- No fake workflow progress
- Frontend unavailable / disconnected projection
- Worker tick continues when telemetry write fails

---

## 10. Remaining blockers for authenticated live browser telemetry

1. No verified per-user exchange ownership binding.
2. Operator-local Bybit credentials are not tenant-scoped.
3. `PRIVATE_DATA_READS_ENABLED=false` and SSE remain correctly disabled.
4. Migration `20261104_0002` not applied (manual ops decision).
5. Browser LIVE depends on same-machine Next.js → loopback API process topology.

---

## 11. Recommended next milestone

**Phase 3C — Authenticated ownership-bound observability**

1. Apply and verify ownership migration under controlled ops.
2. Bind operator exchange accounts to authenticated users with RLS.
3. Introduce authenticated, ownership-gated snapshot reads (still no Host-header trust).
4. Keep order mutation HTTP and SSE off until ownership proofs and audit logging ship.
5. Expand chart correlation with public market-data adapter refresh for longer history without inventing markers.

---

## Success statement

CryptoNova Agent Studio is functionally verified from real application code using safe mocked inputs. The UI accurately presents worker decisions, risk outcomes, and supported evidence without implying unverified live trading, exposing private data to arbitrary clients, or weakening existing controls.
