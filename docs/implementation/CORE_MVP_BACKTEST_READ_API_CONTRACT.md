# CryptoNova — Backtest Read API Contract (Prompt 68B)

## Feature gate

| Flag | Default | Behavior |
| --- | --- | --- |
| `BACKTEST_READ_API_ENABLED` | `false` | When false: `/status` reports disabled; data routes return **503** |
| `BACKTEST_RESULTS_DIR` | unset → `data/backtests` | Allowed root for artifact discovery |

Access uses the same **loopback/operator diagnostic** gate as the paper read API.

## Artifacts

Canonical file: `{results_dir}/{run_id}_report.json` where `run_id` matches `bt_[A-Za-z0-9]{8,32}`.

Written atomically by `agent.backtest.artifacts.persist_run_artifact` (tmp + replace). GET handlers never create directories or mutate files.

## Routes (GET only)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/v1/backtests/status` | Always callable; gated detail when enabled |
| GET | `/api/v1/backtests/runs` | Paginated summaries (`limit`≤100) |
| GET | `/api/v1/backtests/runs/{run_id}` | Detail + assumptions |
| GET | `/api/v1/backtests/runs/{run_id}/metrics` | Counters + embedded 67A analytics |
| GET | `/api/v1/backtests/runs/{run_id}/trades` | Closed trades + open summaries |
| GET | `/api/v1/backtests/runs/{run_id}/equity` | Marked vs realized series |
| GET | `/api/v1/backtests/runs/{run_id}/decisions` | Per-bar decisions + submit/fill join |
| GET | `/api/v1/backtests/runs/{run_id}/orders` | Submit records + rejection breakdown |

**No POST / run / execute endpoints in 68B.**

## Security

- Strict `run_id` validation (no path segments)
- Resolve under results root; reject path/symlink escape
- Max artifact size 8 MiB
- Corrupt JSON → 422
- Missing run → 404
- Disabled → 503
- No arbitrary filesystem reads

## Next.js proxies

Same-origin `/api/backtests/*` → FastAPI allowlist in `public-backtest-proxy.ts`.
