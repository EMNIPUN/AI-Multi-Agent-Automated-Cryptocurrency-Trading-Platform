# CryptoNova — Master Prompt 67B Analytics Dashboard Report

| Field | Value |
| --- | --- |
| Status | COMPLETE |
| Date | 2026-11-08 |
| Depends on | Prompt 67A analytics APIs |

---

## Implementation summary

`/analytics` no longer renders `analyticsFixture` SAMPLE metrics. It loads read-only paper analytics through existing Next.js proxies to FastAPI 67A endpoints, with session selection, symbol/exit-date filters, paginated closed trades, symbol breakdown, and labeled equity/drawdown series.

## Files changed

| Path | Role |
| --- | --- |
| `apps/web/src/app/analytics/page.tsx` | Suspense shell |
| `apps/web/src/app/analytics/AnalyticsDashboard.tsx` | Main dashboard UI |
| `apps/web/src/lib/paper/types.ts` | 67A analytics DTOs |
| `apps/web/src/lib/paper/api.ts` | Typed fetch helpers |
| `apps/web/src/lib/paper/analytics-format.ts` | Decimal/status/date helpers |
| `apps/web/src/lib/paper/analytics-ui.test.ts` | Frontend unit tests |
| `apps/web/src/app/paper/page.tsx` | Link to analytics for selected session |
| `docs/implementation/CORE_MVP_IMPLEMENTATION_ROADMAP.md` | 67B DONE; 68 next |

## API integration

Proxies (unchanged allowlist):

- `/api/paper/sessions/{id}/analytics`
- `.../analytics/trades`
- `.../analytics/equity`
- `.../analytics/symbols`

Browser never opens SQLite/Postgres directly. Decimal fields remain strings until display formatting. Optional metrics honor `empty` / `unavailable` / `unbounded` — no fabricated 0% win rate.

## Session / filter behavior

- Sessions from `GET /api/paper/sessions`
- URL params: `session`, `symbol`, `series`, `exit_from`, `exit_to`, `offset`
- Exit dates convert to UTC ms (`exit_from_ms` / `exit_to_ms`)
- Equity series is always **session-wide** and labeled as such (not reshaped by symbol/date trade filters)
- Marked equity vs realized balance (available + reserved) never mixed

## Empty / error states

| State | UI |
| --- | --- |
| `PAPER_READ_API_ENABLED=false` | Disabled banner; no fixtures |
| Missing DB | Explicit missing-journal notice |
| No sessions | Empty sessions notice |
| No closed trades | Metrics show n/a / empty statuses |
| No equity points | Equity panel unavailable message |
| Warnings | Data-quality list from API |
| HTTP/network failure | Error card + Retry |

## Safety

- No paper mutations, broker auto-attach, live orders, OpenAI, Gate 63, deploy, or git push
- Flags preserved OFF by default (`PAPER_READ_API_ENABLED`, broker auto-attach, portfolio risk auto-wire)

## Tests

| Command | Result |
| --- | --- |
| `vitest run` `analytics-ui.test.ts` + `paper-ui.test.ts` | **16 passed** |
| `npm run typecheck` (`tsc --noEmit`) | **exit 0** |
| `npm run lint` | **No ESLint warnings or errors** |
| `pytest tests/test_core_paper_analytics.py` + `test_core_paper_analytics_api.py` | **22 passed** |
| `pytest` paper API + portfolio risk + paper integration | **31 passed**, **1 failed** (pre-existing) |

Pre-existing failure (not introduced by 67B): `test_core_paper_integration.py::test_no_cloud_writes_in_paper_modules` asserts the token `supabase` is absent from paper modules; after the SQLite→Supabase SoT cutover, `agent/paper/read_store.py` imports `supabase_sot_enabled`. Literal string scan is stale relative to the approved cutover.

## Known limitations

1. Requires `PAPER_READ_API_ENABLED=true` on loopback to view live data.
2. Symbol breakdown does not include profit factor/expectancy columns (not on 67A symbol DTO).
3. Equity panel is session-wide only under trade filters (by design).
4. Sorting of trades table not implemented (API order preserved).
5. Component-level React Testing Library coverage is format/proxy-focused; dashboard wiring is covered via typed client + format helpers rather than full browser e2e.

## Next milestone

**Prompt 68 — Deterministic Multi-Agent Backtesting.**
