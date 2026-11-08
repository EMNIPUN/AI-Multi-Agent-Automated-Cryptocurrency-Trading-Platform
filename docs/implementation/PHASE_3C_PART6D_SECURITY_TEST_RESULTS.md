# Phase 3C Part 6D — Security Test Results

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Python adapter suite | **14 passed** (`tests/test_phase3c_part6d_testnet_adapter.py`) |
| Frontend vitest | **23 passed** |
| TypeScript | **PASS** (`tsc --noEmit` exit 0) |
| ESLint | **PASS** (0 issues) |
| Production build | **PASS** (`npm run build` → `BUILD=0`) |
| Real Bybit / cloud / migrations / git | **None** |

Exact exits (this session): Python adapter **14 passed** (`PYTEST=0`); `tsc --noEmit` **TSC=0**; `next lint` **LINT=0**; Vitest **23 passed** (`VITEST=0`); `npm run build` **BUILD=0** (SWC native binary warning present; WASM fallback compiled successfully). Route `/api/exchange/bindings/[id]/simulate-verify` included in production route table.

---

## Fail-closed matrix

| # | Case | Result |
|---|------|--------|
| 1 | Invalid credentials | **PASS** |
| 2 | Wrong environment (record + response) | **PASS** |
| 3 | Network timeout | **PASS** |
| 4 | Rate limit | **PASS** |
| 5 | Malformed response | **PASS** |
| 6 | Credential owner mismatch | **PASS** |
| 7 | Permission mismatch | **PASS** |
| 8 | Duplicate verification in-flight | **PASS** |
| 9 | Revoked credentials | **PASS** |
| 10 | Unexpected adapter exception | **PASS** |
| — | Success does not activate / enable private reads | **PASS** |
| — | Operator env ref blocked | **PASS** |
| — | HTTP simulate-verify keeps pending | **PASS** |
