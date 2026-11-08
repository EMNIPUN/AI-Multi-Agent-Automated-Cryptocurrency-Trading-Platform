# CryptoNova — Backtest Run API Contract (68C)

| Field | Value |
| --- | --- |
| Milestone | Core MVP 68C |
| Gate | `BACKTEST_RUN_API_ENABLED` (default **false**) |
| Prefix | `/api/v1/backtests` |
| Auth | Loopback operator diagnostic (same as paper/backtest read) |

---

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/run-capabilities` | Supported symbols/intervals/limits + gate flags |
| POST | `/runs` | Enqueue one historical backtest (explicit only) |
| GET | `/jobs/{job_id}` | Poll job lifecycle (`btj_*`) |
| GET | `/runs/{run_id}/status` | Job id or completed `bt_*` artifact status |

Read endpoints from 68B remain GET-only and use `BACKTEST_READ_API_ENABLED`.

**GET never starts execution.**

## POST body (validated)

```json
{
  "symbol": "BTCUSDT",
  "market_type": "spot",
  "interval": "15",
  "start_ms": 1704067200000,
  "end_ms": 1706745600000,
  "initial_capital": "1000",
  "fee_rate": "0.001",
  "slippage_bps": "5",
  "risk_mode": "signal_only",
  "data_source": "bybit_public",
  "idempotency_key": "optional-client-key"
}
```

Forbidden fields: `dataset_path`, `journal_path`, `code`, `script`, `url`, `command`.

`offline_fixture` requires `dataset_hash` (64 hex) — never a filesystem path.

## Lifecycle

`QUEUED → RUNNING → COMPLETED | FAILED`

On process restart, in-flight jobs become `INTERRUPTED` and are never presented as completed.

Cancellation is **not** implemented (no `CANCELLED` claims).

## Security

- Feature gate default OFF.
- Loopback / operator diagnostic required when enabled.
- Next.js same-origin proxy: Origin/Referer check on POST; 16 KiB body cap.
- Strict `Content-Type: application/json`.
- Idempotency via body `idempotency_key` or `Idempotency-Key` header.
- Isolated `bt68a_*.sqlite3` journals under results; no operator paper journal writes.
- Does not flip `PAPER_*`, `AGENT_ALLOW_LIVE`, or `LLM_AGENTS_ENABLED`.

## Resource limits (defaults)

| Limit | Default |
| --- | --- |
| Max candles / run | 5000 |
| Max range | 90 days |
| Max simultaneous | 1 |
| Max queued | 2 |
| Max runtime | 600 s |
| Max dataset file | 8 MiB |
| Max report | 8 MiB |

Env overrides: `BACKTEST_MAX_*` (see `.env.example`).

## Worker model

Single daemon thread + in-process queue (max concurrent = setting). No unbounded thread pool.
