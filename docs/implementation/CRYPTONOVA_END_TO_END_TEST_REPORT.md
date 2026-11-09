# CryptoNova — End-to-End Test Report

## This pass

`tests/test_core_backtest_69e.py::test_storage_unavailable_and_shadow_status_does_not_call_a_model` and `tests/test_core_70a_audit.py`

**6 passed, 0 failed, 0 skipped.**

Live probes after the API restart, against `127.0.0.1:8200`:

| Probe | Result |
| --- | --- |
| `GET /api/v1/backtests/shadow-status` | 200. Revision `20261108_0011`, pending empty, historical news backtest invalid, budget flag true, model not called |
| `GET /api/v1/llm/status` | 200. Disabled, provider not called, budget storage `postgres`, daily budget 1.0, 0 calls this hour |
| `GET /api/v1/signals/status` | 500. `signal_cloud_owner_user_id_unset` on the restarted process |

## Earlier on this same database

The 70B.1 integration script: **59 passed, 0 failed, 0 skipped.** That covered news persistence, alerts, LLM audit replay, revision selection, the append-only trigger, and budget concurrency. It is not re-counted as a new run.

## Not run

The full backend suite, frontend vitest, type check, and production build were not run. Unsigned page redirects were observed in 70B.1. Signed-in dashboard clicks were not run. Skipped database tests from older suites are not treated as passed.

No paid OpenAI call, Telegram send, or exchange order was part of any test.
