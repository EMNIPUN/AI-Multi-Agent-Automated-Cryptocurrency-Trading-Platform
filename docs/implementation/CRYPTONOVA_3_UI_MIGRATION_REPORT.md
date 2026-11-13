# CryptoNova 3 — UI migration report

Date: 2026-11-10

This pass continues the Obsidian Amber foundation. The theme, sidebar, topbar, and navigation were not rebuilt.

## Phases

| Phase | Result |
|---|---|
| A Shared templates | Added `templates.tsx`, `ExecutionMode`, and aliases `FinancialValue`, `RiskVerdict`, `DataPanel`, `ChartPanel`. |
| B AI command center | `/dashboard` renders `DashboardHome` again instead of redirecting to `/orchestrator`. Orchestrator context opens in a sheet below 1280px. Agents, live analysis, and LLM use `AiWorkspaceTemplate`. |
| C Autonomous operations | `/autonomy` and `/paper` use `OperationsTemplate`. Existing supervisor commands are unchanged. |
| D Trading desk | `/markets` and `/positions` use `TradingTerminalTemplate`. `/portfolio` and `/risk` use `OverviewTemplate`. |
| E Research | News, strategy, and analytics use `ResearchTemplate`. Backtesting dropped the black gradient hero. |
| F System and auth | Notifications, settings, and exchanges use `SettingsTemplate`. System health uses `OverviewTemplate`. Marketing and auth shells were left in place. |
| G QA | Typecheck and unit tests recorded below. Authenticated screens were not visually confirmed. |

## New components

- `apps/web/src/components/design-system/templates.tsx`
- `apps/web/src/components/design-system/ExecutionMode.tsx`

No duplicate shell components were deleted. `PageFrame` remains the single heading implementation.

## Routes

Every previous URL still resolves, including `/autonomy`. `/dashboard` is a real overview again.

## Tests

| Command | Result |
|---|---|
| `npx tsc --noEmit` | Pass |
| `npx vitest run` | 16 files, 89 tests, 0 failed |
| `npx next lint` | Exit 0. One warning: command-palette options were missing `aria-selected`. That attribute is now set. |
| `npx next build` | Compile and type check passed. Page-data collection then failed with `ENOENT` for existing routes `/api/exchange/bindings/[id]/revoke` and `/api/backtests/shadow-status` while `next dev` was already using `.next`. Those route files are present and were not modified. Playwright is not configured in `apps/web`. |

## Verification

| Check | Result |
|---|---|
| Dark / light theme | Tokens unchanged from the foundation pass. This pass did not re-test every route in both themes. |
| Authenticated UI | Not verified. Opening `/dashboard` with no session lands on `/login?next=%2Fdashboard`. The route no longer server-redirects to `/orchestrator`. No auth bypass was added. |
| Responsive | Orchestrator context is a sheet below the `xl` breakpoint. Signed-in checks at 390 / 768 / 1024 / 1440 / 1920 were not run. |
| Screenshots | The browser window was hidden, so no signed-in screenshot was captured. |

## Performance

No new polling loop and no new chart library. Markets still uses the existing lightweight-charts client component. Live prices stay static text.

## Blockers

- Signed-in visual QA needs an existing local user session. This migration does not create one.
- Positions filtering, column visibility, and TanStack Table were not added. The current positions panel remains the read-only view.
- React Flow agent graphs were not rebuilt. `/agents/live` still uses the existing studio.
- Playwright was not run in this pass.

## Safety

No exchange order path, risk limit, strategy, auth rule, or database migration was changed.
