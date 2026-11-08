# CryptoNova — Paper Analytics API Contract (67A)

Read-only FastAPI surface over local SQLite paper journal analytics.

## Feature gate

| Setting | Default | Behavior |
| --- | --- | --- |
| `PAPER_READ_API_ENABLED` | `false` | All paper + analytics GETs return 503 when disabled |
| Access | Loopback / existing operator restrictions | Same as Prompt 65B paper read API |
| Mutations | None | No POST/PUT/PATCH/DELETE analytics routes |
| DB init on GET | Forbidden | Missing SQLite → error; file not created |

Decimals serialize as decimal **strings**. Optional metrics use `{ value, status, reason }`.

---

## Endpoints

Base: `/api/v1/paper`

### `GET /sessions/{session_id}/analytics`

Session summary metrics + symbol breakdown + drawdown summaries.

**Query**

| Param | Type | Notes |
| --- | --- | --- |
| `symbol` | string? | Optional symbol filter |
| `exit_from_ms` | int? | Inclusive UTC ms exit lower bound |
| `exit_to_ms` | int? | Inclusive UTC ms exit upper bound |

**Responses**

| Code | Meaning |
| --- | --- |
| 200 | `PaperAnalyticsResponse` |
| 400 | Invalid session id / filters |
| 404 | Session or DB missing |
| 503 | Feature disabled |

Notable fields: `win_rate_pct`, `profit_factor`, `expectancy`, `realized_return_pct` as `OptionalMetric`; `max_drawdown_marked` / `max_drawdown_realized_balance`; `data_quality_warnings`; `data_label=SIMULATED / PAPER ONLY`.

### `GET /sessions/{session_id}/analytics/trades`

Paginated closed-trade metrics.

**Query:** `symbol`, `exit_from_ms`, `exit_to_ms`, `limit` (bounded), `offset`.

### `GET /sessions/{session_id}/analytics/equity`

Equity observation points.

**Query:** `series=marked|realized_balance` (implementation default documented in router).

### `GET /sessions/{session_id}/analytics/symbols`

Per-symbol breakdown (same filters as summary).

---

## Next.js proxy

`apps/web/src/app/api/paper/sessions/[sessionId]/analytics/**` proxies to FastAPI with the same public-paper-proxy security as other paper routes. Does not weaken loopback/operator checks.

---

## Safety

- Read-only `PaperReadStore` (SQLite `mode=ro`).
- No broker attach, no portfolio risk enablement.
- No exchange / Bybit private / OpenAI / Supabase calls.
- Results labeled simulated paper only.
