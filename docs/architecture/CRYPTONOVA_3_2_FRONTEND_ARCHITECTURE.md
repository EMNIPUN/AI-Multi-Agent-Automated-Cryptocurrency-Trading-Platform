# CryptoNova 3.2 — Frontend architecture

Public URLs are unchanged. Route files in `apps/web/src/app` stay thin; heavy screens moved under `src/features/*`.

```text
apps/web/src/
├── app/                      thin routes (+ orchestrator/* and autonomy/* page-local components)
├── components/
│   ├── design-system/        FinancialValue, MetricCard, StatusIndicator, DataFreshness, ReasonList, DataTable, ExecutionMode, Error/Empty/Loading…
│   ├── charts/               EquityCurveChart (recharts, single series, dynamic import)
│   ├── market/               MarketCandleChart (lightweight-charts; theme-reactive, ResizeObserver)
│   └── layout/               AppShell (mounts ExecutionStateProvider), GlobalStatusBar
├── features/
│   ├── dashboard/            DashboardHome + realizedEquitySeries
│   ├── agents/               AgentWorkspace, AgentGraph (React Flow), AgentInspector, LiveAnalysisPanel, agent-graph.ts
│   ├── markets/              MarketsTerminal + watchlist storage
│   ├── positions/            PositionsWorkspace + position-rows normalizer
│   └── paper/                PaperCockpit
├── hooks/use-polled-resource.ts   single-subscription polling (abort, visibility pause, keep-last-good)
├── lib/api/                  client.ts (ApiResult), orchestrator.ts (typed contracts + fetchers), execution-state.ts
├── lib/formatting/           decimal (string-precise), time, reason-codes, status
└── providers/ExecutionStateProvider.tsx  one shared poll of automation/orchestrator/risk/market facts
```

## Data layer

- `lib/api/client.ts` returns `ApiResult<T>` (`ok | {code, message, status, at}`) instead of throwing, so every page renders honest error/unavailable states.
- `lib/api/orchestrator.ts` mirrors the FastAPI payload builders (`_status_tool`, `_report_tool`, `build_autonomy_snapshot`, `per_agent_runtime_status`, `risk_feed`, `/diagnostics`, `Orchestrator.handle`).
- `usePolledResource` owns one subscription per resource: aborts in-flight requests on unmount/refetch (no StrictMode double calls), pauses when hidden, refreshes on return.
- `ExecutionStateProvider` is mounted once in `AppShell`; status bar, footer, dashboard, risk, positions, portfolio, system and settings consume it instead of polling the same four endpoints.
- No TanStack Query was added: existing adapters already own caching/polling and the new hook covers the remaining pages.

## Trust boundaries

- Browser never decides authorization. `RequireAuth` is a UI gate; FastAPI verifies JWTs; operator controls go through the loopback-only `operator-proxy`.
- No live mutation endpoint is called from any new component. Supervisor commands (`/api/orchestrator/command`) are the only writes, PAPER only, and show state only after the server acknowledges.
- The Orchestrator reply badge is derived from `openai_called`, `used_fallback`, `fallback_reason`, `result_envelopes` — a fallback is never labelled OpenAI.

## Build & test

- `next.config.ts` honours `NEXT_DIST_DIR`; `npm run build:isolated` builds into `.next-build` so a running `next dev` (owner of `.next`) cannot corrupt page-data collection.
- `vitest` runs `src/**/*.test.ts`; Playwright (`e2e/`) has `unauthenticated`, `setup` and `authenticated` projects; credentials come from env or gitignored `.env.e2e.local`.
