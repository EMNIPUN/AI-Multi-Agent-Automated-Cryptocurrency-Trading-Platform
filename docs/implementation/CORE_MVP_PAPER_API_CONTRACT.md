# CryptoNova — Paper Read API Contract (Prompt 65B)

| Field | Value |
| --- | --- |
| Feature gate | `PAPER_READ_API_ENABLED` (default **false**) |
| DB path | `PAPER_SQLITE_PATH` (default `data/cryptonova_paper.sqlite3`) |
| Access | Loopback operator diagnostic (`assert_operator_local_diagnostic`) when enabled |
| Mutations | **None** — GET only |
| Auto-attach | `PAPER_BROKER_AUTO_ATTACH = False` (unchanged) |

---

## Routes

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/paper/status` | Works when disabled (reports gate); when enabled requires loopback |
| GET | `/api/v1/paper/sessions` | Paginated session list |
| GET | `/api/v1/paper/sessions/{session_id}` | Session summary |
| GET | `/api/v1/paper/sessions/{session_id}/account` | Cash / reserved / realized / marked equity status |
| GET | `/api/v1/paper/sessions/{session_id}/positions` | Filters: `status`, `symbol`, `limit`, `offset` |
| GET | `/api/v1/paper/sessions/{session_id}/orders` | Filters: `status`, `symbol`, `source_signal_id` |
| GET | `/api/v1/paper/sessions/{session_id}/fills` | Filters: `symbol` |
| GET | `/api/v1/paper/sessions/{session_id}/events` | Journal events |
| GET | `/api/v1/paper/orders/by-signal/{signal_id}` | Link lookup — never creates trades |

Disabled data routes → **503** with `paper_read_api_disabled`. Missing session → **404**. Invalid ids → **400**.

---

## Serialization

- Monetary fields: **decimal strings** (no binary float).
- Timestamps: epoch **milliseconds** (UTC semantics at display layer).
- Every payload includes `data_label: "SIMULATED / PAPER ONLY"` where applicable.
- Unrealized / marked equity: only when persisted marks exist; otherwise `unavailable` / `stale_or_partial`.

---

## Read store guarantees

`PaperReadStore` opens SQLite `mode=ro`, never creates files/dirs, never runs DDL, never mutates rows.

---

## Next.js proxy

Same-origin GET allowlist via `apps/web/src/lib/security/public-paper-proxy.ts` → `/api/paper/*`.

No POST/PUT/PATCH/DELETE paper proxies.
