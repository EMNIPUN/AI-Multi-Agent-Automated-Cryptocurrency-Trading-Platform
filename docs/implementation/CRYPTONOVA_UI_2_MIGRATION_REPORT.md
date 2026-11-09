# CryptoNova UI 2.0 Migration Report

**Completed:** 2026-11-09  
**Scope:** `apps/web` frontend redesign (phases 0–7)  
**Safety:** No live trading, risk policy, credential, or backend contract changes  

---

## Phase status

| Phase | Status |
|-------|--------|
| 0 Baseline | Done |
| 1 Design system | Done |
| 2 Global shell | Done |
| 3 Orchestrator / agents | Done |
| 4 Trading desk | Done (theme purge + risk center) |
| 5 Research | Done (white/* purge on news/backtesting) |
| 6 System / auth | Done (settings appearance; cyan→brand) |
| 7 Polish / docs | Done |

---

## Baseline → final QA

| Check | Baseline | Final |
|-------|----------|-------|
| `npm run typecheck` | Pass | Pass |
| `npm run test` | 61 pass | **61 pass** |
| Light default | Yes | Yes (`cryptonova.theme.v2`) |
| Density persist | N/A | `cryptonova.density.v1` |

---

## Components created

**`components/design-system/`**  
AppPageHeader, PageSection, StatCard, StatusBadge, ModeIndicator, RiskIndicator, EmptyState, ErrorState, LoadingState, DataFreshnessBadge, MetricValue  

**`components/layout/`**  
AppTopbar, GlobalStatusBar, CommandPalette  

## Components reused

- command-center: PageFrame, SectionPanel, ModeBadge, AgentStatusList, MetricTile  
- shared: EmptyState, PageMotion  
- orchestrator: CommandChat, Reply, StatusStrip  
- ui/* shadcn, magicui (BorderBeam on marketing/beams only)  

## Components removed

- `components/shared/PageHeader.tsx`  
- `components/SiteNav.tsx`  

## Routes migrated (shell + tokens)

All 23 routes inherit new AppShell. Notable page updates:

- `/orchestrator` — three-region layout, flex height, client session rail, tool trace panel  
- `/agents/live` — clarified “analysis ≠ live trading”  
- `/risk` — RiskIndicator + status badges  
- `/settings` — Appearance (theme + density)  
- Trading/research hotspots — `white/*` → semantic tokens (~36 files)  

## Navigation

- Notifications added under System in `lib/nav.ts`  
- Labels aligned to UI 2.0 brief  
- Ctrl+K navigate-only command palette  

## Light / dark verification

- Semantic tokens for paper/live/halted/stale/info/chart  
- Bulk purge of `text-white/*`, `border-white/*`, `bg-white/*`  
- Remaining literal `#F7A600` limited to BorderBeam/Particles/chart series props (documented brand hex)  
- Hardcoded `#080D19` / `#253348` panels replaced with `bg-card` / `border-border`  

## Accessibility findings

- Status badges include text labels (not color alone)  
- Command palette keyboard (Ctrl+K) + dialog focus  
- GlobalStatusBar `role="status"`  
- Remaining: deeper screen-reader pass on markets tables (noted as follow-up)  

## Performance findings

- No new heavy chart libraries  
- Magic UI still present on landing/beams; tick animation not added to order tables  
- Orchestrator removed brittle `calc(100svh-9rem)` in favor of flex fill  

## Safety unchanged

- PAPER / LIVE locked messaging preserved  
- No live/testnet order actions  
- Chat proxies unchanged  
- Auth flows preserved (`variant="brand"` alias of former cyan)  

## Remaining issues / follow-ups

1. Markets page still uses a custom hero (tokenized) — optional further PageFrame alignment  
2. BorderBeam still takes hex props — consider CSS-var-aware wrapper later  
3. Playwright e2e not added (per plan)  
4. Full WCAG audit of every data table pending  
5. Production `next build` not re-run in this session (typecheck + vitest green)

## Design docs

- [docs/design/CRYPTONOVA_UI_2_DESIGN_SYSTEM.md](../design/CRYPTONOVA_UI_2_DESIGN_SYSTEM.md)  
- [docs/design/CRYPTONOVA_UI_2_ROUTE_BLUEPRINT.md](../design/CRYPTONOVA_UI_2_ROUTE_BLUEPRINT.md)  

## Related

- Prior audit: [CRYPTONOVA_UI_AUDIT_REPORT.md](./CRYPTONOVA_UI_AUDIT_REPORT.md)  
