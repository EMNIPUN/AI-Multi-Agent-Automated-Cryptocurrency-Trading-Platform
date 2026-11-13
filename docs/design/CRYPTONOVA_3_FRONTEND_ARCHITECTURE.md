# CryptoNova 3 — Frontend architecture

Public URLs are unchanged. Route groups were not introduced: the App Router files in `apps/web/src/app` are already thin, and a mechanical move would not change behavior.

## Shell

`AppShell` keeps marketing and auth outside the workspace. Authenticated routes render inside the sidebar, 56px topbar, and the runtime status bar. Navigation lives in `src/lib/nav.ts`. Overview is `/dashboard`.

## Templates

`src/components/design-system/templates.tsx` wraps the existing `PageFrame`:

| Template | `data-template` | Routes |
|---|---|---|
| OverviewTemplate | overview | `/dashboard`, `/portfolio`, `/risk`, `/system` |
| TradingTerminalTemplate | terminal | `/markets`, `/positions` |
| AiWorkspaceTemplate | ai | `/orchestrator`, `/agents`, `/agents/live`, `/llm` |
| OperationsTemplate | operations | `/autonomy`, `/paper` |
| ResearchTemplate | research | `/news`, `/strategy`, `/backtesting`, `/analytics` |
| SettingsTemplate | settings | `/settings`, `/settings/exchanges`, `/notifications` |

Shared status pieces: `StatusBadge`, `ExecutionMode`, `RiskIndicator` (`RiskVerdict`), `MetricValue` (`FinancialValue`), `DataPanel` / `ChartPanel` (section panel aliases).

## Data

Pages keep their existing API clients and fetch hooks. No TanStack Query layer was added; the current fetch adapters already own caching and polling. Tables stay on the existing panel components. `@tanstack/react-table` is not installed, and adding it was not required to keep positions readable.

## Safety

The UI does not authorize exchange orders. Live state comes from supervisor, risk, and automation endpoints. A connected exchange key is described as a read connection, not execution permission.
