# Phase 4D Gate B0 — Legacy Outbox Recovery Design

**Sync enabled this session:** no  
**Cloud import executed:** no  

## Current authoritative state

| Metric | Value |
| --- | --- |
| `cloud_sync_outbox` rows | **0** |
| `signal_history` rows | **3** |
| Immediate `PERMANENT_FAILURE` candidates in outbox | **0** |

**Note:** History without matching outbox rows implies pre-atomic-enqueue era or cleared outbox. Those decisions are **not** discarded; they remain in SQLite `signal_history` and need optional backfill **after** Gate D/E approval — not now.

## How incomplete payloads are handled (code)

`apps/api/app/signals/cloud_sync.py`:

- `is_legacy_summary_payload` → mark `PERMANENT_FAILURE` with `legacy_summary_incomplete`  
- Invalid `4D.1.0` envelope → permanent `payload_invalid:*`  
- Full payloads validated then idempotent upsert  

This prevents false cloud success and does **not** delete `signal_history`.

## Deterministic recovery / backfill design (disabled until approved)

### Phase R1 — Inventory (safe, local)

1. Scan outbox for legacy summaries / permanent failures.  
2. Scan `signal_history` for `decision_id`s lacking a `SYNCED` outbox event.  
3. Emit reconciliation report only (counts + decision_ids).  

### Phase R2 — Rebuild outbox from local history (local only)

For each missing/failed event, rebuild envelope from durable columns:

- `decision_id`, `idempotent_key`, `symbol`, `category`, `interval`, `action`, …  
- `contributions_json`, `risk_json`, `levels_json`, `market_json`, `indicators_json`  

Set `payload_schema_version=4D.1.0`, `execution_allowed=false`, `legacy=true` (marker), `rebuilt_from=signal_history`.

**Never fabricate** missing indicator keys; omit or leave empty as stored.

Idempotent `event_id = signal:{decision_id}` — do not double-insert.

### Phase R3 — Cloud upsert (Gates C/D/E)

Only after DDL + owner binding + write/sync approval. Upsert by `decision_id` / owner+idempotent_key. Retain SQLite rows.

## Operator action

None required for Gate B0 DDL readiness beyond acknowledging this design. Do **not** enable sync to “clear” legacy rows.
