# CryptoNova 3.2 — Frontend upgrade report

Date: 2026-11-15 · Scope: `apps/web` only · Backend untouched (no trading, risk, strategy, auth, migration or spend-limit changes).

## 1. Summary

The Obsidian Amber foundation (tokens, 252/64 px sidebar, 56 px topbar, navigation, Ctrl+K, density, `/autonomy`) was kept. Work went into: a repaired production build, a Playwright harness, a shared financial component layer, typed API contracts with a single execution-state subscription, and rebuilt Dashboard, Orchestrator, Agents, Live Analysis, Markets, Positions, Portfolio, Risk, Paper, LLM, System, Notifications and Settings screens. Every status label now reads a backend fact — including the honest **LIVE armed · Approve per order** state this machine is actually in.

## 2. Build failure — root cause and resolution

- **Observed again:** `next dev --turbopack` (PID on :3000) owned `.next` while the previous `next build` wrote to the same directory; page-data collection then read route manifests the dev server had rewritten → `ENOENT` for existing API routes.
- **Fix:** `next.config.ts` reads `NEXT_DIST_DIR`; `npm run build:isolated` (scripts/build-isolated.mjs) builds into `.next-build` while dev keeps `.next`. `.next-*` is gitignored.
- **Result:** full build completed with `next dev` still running — compile, type check, page-data collection, 44/44 static pages (`build exit: 0`). Shared first-load JS unchanged at 106 kB.
- **Caveat:** the shared-`.next` failure was not re-triggered on purpose (it would have corrupted the live dev server); the diagnosis rests on the reproduced conditions plus the clean isolated build.

Second blocker found on the way: `package-lock.json` carried 48 `node_modules/esbuild/node_modules/@esbuild/*` entries with no `version`, which made npm 10.9 abort every install (`Invalid Version:`). The invalid entries were removed and the hidden lockfile regenerated.

## 3. Completed improvements (by phase)

| Phase | Delivered |
|---|---|
| 0 | Isolated build; Playwright 1.49 + axe + Chromium; `e2e/` with public, auth-setup, workspaces (19 routes × 5 viewports × 2 themes) and a11y specs; vitest excludes e2e |
| 1 | `FinancialValue`, `MetricCard`, `StatusIndicator`, `DataFreshness`, `ReasonList`, `DataTable` (TanStack 8.20), `ExecutionMode` (armed states), `ErrorState` (code + time); `lib/formatting` (string-precise decimals, time, reason-code catalog, status normalizer); `lib/api` typed contracts; `usePolledResource`; `ExecutionStateProvider` |
| 2 | Dashboard (status → KPIs → equity chart/agents/analysis → events); Orchestrator (threads rail from server, context inspector, honest orchestration badge, `result_envelopes` tool trace, copy, cancel, scroll-to-latest, Enter/Shift+Enter); Agents (React Flow graph + inspector + timeline); Live Analysis panel; LLM dashboard with audit grid |
| 3 | Markets terminal (watchlist search/add/favorites, timeframe toolbar, EMA toggle, theme-reactive resizable chart, summary, metrics, agent analysis); Positions `DataTable` with filters + detail sheet; Portfolio source switch; Risk Center |
| 4 | Autonomy: activity timeline, agent runtime, real lane badges; Paper cockpit with confirm-step controls + archive tab |
| 6 | System health probes + runtime facts; Notifications from real feeds; Settings connection health from live state |
| 7 | tsc / lint / vitest / isolated build / public e2e / login axe — all green |

## 4. Changed files

Modified (28): `.gitignore`, `next.config.ts`, `package.json`, `package-lock.json`, `tsconfig.json` (Next added `.next-build/types`), `vitest.config.ts`, routes `agents`, `agents/live`, `autonomy/AutonomousWorkspace`, `llm/LlmDashboard`, `markets`, `notifications`, `orchestrator/OrchestratorCommandChat`, `orchestrator/OrchestratorWorkspace`, `paper` (→ `PaperArchive`), `portfolio`, `positions`, `risk`, `settings`, `system`; components `dashboard/DashboardHome` (re-export), `design-system/{ErrorState,ExecutionMode,index}`, `layout/{AppShell,GlobalStatusBar}`, `market/MarketCandleChart`, `ui/dropdown-menu` (+`DropdownMenuCheckboxItem`).

## 5. New components / modules

`components/design-system/{FinancialValue,MetricCard,StatusIndicator,DataFreshness,ReasonList,DataTable}`, `components/charts/EquityCurveChart`, `features/{dashboard,agents,markets,positions,paper}/…`, `app/orchestrator/{ConversationRail,ContextInspector,OrchestratorComposer,ToolTraceCard,orchestrator-state}`, `app/autonomy/ActivityTimeline`, `hooks/use-polled-resource`, `lib/api/{client,orchestrator,execution-state}`, `lib/formatting/*`, `providers/ExecutionStateProvider`, `playwright.config.ts`, `e2e/*`, `scripts/build-isolated.mjs`.

## 6. Removed duplication

- Orchestrator's hardcoded 9-agent list that mirrored the supervisor state → replaced by `/agents/runtime` facts.
- Dashboard `SAMPLE` fixtures and hardcoded "PAPER · gates on the status bar" tile → live execution state.
- Status bar / footer / system / settings hardcoded "LIVE off / Trading HTTP Off / 127.0.0.1:8000" → shared provider.
- Notifications no longer derive from the SAMPLE observability snapshot.
- `components/dashboard/DashboardHome.tsx` kept only as a re-export for import stability.
- **Deleted (no importers left):** `PositionsOrdersPanel`, `AgentCommandCenter`, `PipelineViz`, `PaperWorkspace`, `dashboard/DashboardMarkets`, `lib/fixtures/dashboard.ts`, `agents/AgentWorkflowFlow` (hardcoded "DEMO WORKFLOW" graph), `SampleBanner`, legacy `components/StatusBadge`, `EventTimeline`, `OrderLifecycle`.
- Paper archive banners that said "SAMPLE / DEMO" for a disabled/unreachable API now say "unavailable"; the simulated-data notice that `mode="live"` silently hid is shown again.
- Studio `CandleChart` switched from the old slate/emerald palette to Obsidian Amber tokens.

## 7. Route completion matrix

| Route | Status |
|---|---|
| /dashboard, /orchestrator, /agents, /agents/live, /llm, /markets, /positions, /portfolio, /risk, /autonomy, /paper, /system, /notifications, /settings | **IMPLEMENTED BUT UNVERIFIED** (signed-in render). Type-checked, lint-clean, compile 200 on dev server, production build green; no authenticated screenshot. |
| /strategy | **IMPLEMENTED BUT UNVERIFIED** — catalog (product + legacy), markets, intervals, agent weights/rules, decision/risk/regime parameters, live `strategy_version` mismatch warning, backtest runs grid, signal engine. Parameters guarded by a vitest that parses `agent/multi_agent/config.py`. |
| /analytics, /backtesting | **IMPLEMENTED BUT UNVERIFIED** — KPI tiles moved onto the shared `MetricCard`; charts use the shared token-based recharts theme (`lib/charts/recharts-theme.ts`, no hardcoded colours). Existing filters, journals and synthetic/historical labelling kept. |
| /settings/exchanges | **IMPLEMENTED BUT UNVERIFIED** — removed the false "Mainnet activation locked / fixture only" banner; shows server-reported lane state and states a binding is not trading permission. |
| /news | **Unchanged** — already has asset/severity/category/verification filters, timestamps and source provenance on the design-system primitives. |
| /, /login, /signup, /forgot-password, /reset-password | **COMPLETE AND VERIFIED** for the public checks run (shell absent on `/`, 390 px login without overflow, redirects, login axe clean). |

## 8–12. Feature notes

- **Orchestrator:** reply badge from `openai_called` / `used_fallback` / `fallback_reason` / `result_envelopes` → OpenAI, LocalPlanner fallback, API budget blocked, model unavailable, tool failed, data stale, cancelled (unit-tested). Tool trace shows only envelopes returned; analysis tools expand into the agents that actually contributed. Suggestions limited to registry tools. LIVE lane and Approve flow preserved.
- **Agents:** `buildAgentGraph()` renders the real spine from `per_agent_runtime_status`; dashed advisory edge; outcome node from the verified risk verdict (unit-tested). No graph action executes anything.
- **Markets:** lightweight-charts kept; chart repaints on theme change and resizes via ResizeObserver; price precision by magnitude; EMA overlay toggle; watchlist persists in `localStorage`.
- **Positions:** TanStack `DataTable` with numeric-aware sorting of decimal strings, mode/market/status filters, column toggles, pagination, detail sheet; PAPER rows only until TESTNET/MAINNET adapters report positions.
- **Autonomy / Paper:** commands go through `/api/orchestrator/command` only; stop/halt need a confirm click; state shown only after server acknowledgement; equity curve is realized-only and labelled so.

## 13–16. QA evidence

| Check | Result |
|---|---|
| `npx tsc --noEmit` | 0 errors |
| `npx next lint` | 0 warnings / errors |
| `npx vitest run` | 22 files, **113 passed**, 0 failed (was 16 / 89) |
| `npm run build:isolated` | exit 0, 44/44 pages, with `next dev` running |
| Playwright `unauthenticated` | **8 passed** (marketing shell, 390 px login overflow, 6 redirects) |
| Playwright a11y (login, axe WCAG 2.x A/AA) | **1 passed**, no serious/critical violations |
| Playwright `authenticated` (19 routes × 5 viewports × 2 themes, a11y) | **BLOCKED — skipped by operator choice** (no test-account credentials provided). Specs are in `e2e/workspaces.spec.ts` / `e2e/a11y.spec.ts`; run with `CRYPTONOVA_E2E_EMAIL` / `CRYPTONOVA_E2E_PASSWORD` in `apps/web/.env.e2e.local`. Screenshots would land in `apps/web/test-results/screenshots/`. |
| Dev-server compile probes | 14 rewritten routes → HTTP 200 |

Dark/light: tokens unchanged; new components use semantic utilities only; chart palettes switch with the `light` class. **Not visually confirmed signed-in.**

## 17. Accessibility

Headers use `<th scope="col">` + `aria-sort`; status always icon + text; progress bars carry `aria-valuetext`; sheets/dialogs are Radix (focus-trapped); composer is a labelled textbox with Enter/Shift+Enter; `motion-reduce` disables pulses. Signed-in axe runs are blocked as above.

## 18. Performance

No new polling loops beyond: one shared execution-state poll (30 s) and per-page `usePolledResource` subscriptions that abort on unmount and pause when hidden. React Flow and recharts are dynamically imported. Bundle: shared first-load JS 106 kB (unchanged); route sizes in build log. Not profiled in-browser.

## 19. Test counts

tsc 0 · lint 0 · vitest 113/113 · Playwright 9/9 run, 29 skipped (auth-gated) · build exit 0 (re-run after the research pass, 44/44 pages).

## 20. Remaining issues / limitations

1. Signed-in visual, responsive and a11y QA not executed (operator chose to skip). Nothing in sections 7–17 above should be read as visually verified.
2. The research pass (strategy, analytics, backtesting, exchanges, cleanup) was done while both the API and the dev server were down, so those pages have no dev-server compile probe; they are covered by tsc, lint, vitest and the production build only. The API was not restarted because the local `.env` is armed for mainnet.
3. `/news` was reviewed but not redesigned.
4. Public signal evaluation is allow-listed to BTC/ETH/SOL on the backend; the Markets "Agent analysis" panel says so for other symbols.
5. The strategy catalog is a documented mirror of `config.py`; the vitest guard catches drift in the listed constants but not new parameters.
6. `tsconfig.json` was reformatted by `next build` (it adds `.next-build/types`); harmless but noisy in the diff.
