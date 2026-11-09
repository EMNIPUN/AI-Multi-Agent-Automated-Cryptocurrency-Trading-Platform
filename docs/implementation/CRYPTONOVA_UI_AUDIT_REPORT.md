# CryptoNova Entire UI Audit Report

**Scope:** `apps/web` (Next.js 15 command center + marketing + auth)  
**Date:** 2026-11-09  
**Default theme:** Light (Bybit yellow `#F7A600` / charcoal dark override)  
**Routes audited:** 23 `page.tsx` surfaces  

---

## Executive verdict

Brand direction is clear on **Orchestrator**, **settings**, and parts of **agents**, but the trading desk still runs a **dark-only white/opacity dialect** (~200+ `text-white/*` / `border-white/*` / `bg-white/*` hits). Light mode and density will keep fighting the product until that dialect is purged and chrome is unified.

| Severity | Count |
|----------|------:|
| High     | 3 |
| Med      | 4 |
| Low      | 2 |

---

## Surface inventory

### Marketing / auth (5)
`/`, `/login`, `/signup`, `/forgot-password`, `/reset-password`  
Shells: marketing `LandingPage` stack; `AuthShell` for auth. AppShell passthrough.

### AI Command Center (5)
`/dashboard`, `/orchestrator`, `/agents`, `/agents/live`, `/llm`

### Trading Desk (5)
`/markets`, `/portfolio`, `/positions`, `/paper`, `/risk`

### Research (4)
`/news`, `/strategy`, `/backtesting`, `/analytics`

### System (4)
`/settings`, `/settings/exchanges`, `/system`, `/notifications`  
Note: `/notifications` is **not** in sidebar `NAV_GROUPS` (topbar bell only).

### Shared shells
| Shell | Role |
|-------|------|
| `AppShell` | Sidebar + topbar + `RequireAuth` + `PageMotion`; orchestrator fill-height special-case |
| `AppSidebar` | `NAV_GROUPS` from `src/lib/nav.ts` |
| `PageFrame` | In-page title / modes / description |
| `AuthShell` | Auth card + particles |
| `LandingPage` | Marketing chrome |

### Component libraries (approx.)
- shadcn `ui/*` ~28  
- magicui ~18  
- ai-elements ~6  
- command-center 5 (`PageFrame`, `SectionPanel`, `ModeBadge`, `MetricTile`, `AgentStatusList`)

---

## Prioritized findings

### P1 — High — Light default vs dark-only styling
**Evidence:** Grep of `text-white/|border-white/|bg-white/` across `src` (heavy in `NewsDashboard`, `PositionsOrdersPanel`, `WalletBalancePanel`, `markets/page`, `BacktestingDashboard`, `agent-studio`).  
**Impact:** Light theme users see washed / low-contrast copy and borders.  
**Fix:** Replace with `text-foreground`, `text-muted-foreground`, `border-border`, `bg-muted/*`.

### P2 — High — Two visual systems in parallel
**Evidence:** PageFrame + `cn-panel` on orchestrator/settings/agents vs custom `rounded-3xl border-white/10` heroes on markets/backtesting/studio.  
**Impact:** Product feels unfinished; density and spacing rules differ page-to-page.  
**Fix:** Migrate hotspots to PageFrame / SectionPanel / token panels.

### P3 — High — Double page titles
**Evidence:** AppShell topbar title map + PageFrame `<h1>` on most dashboards.  
**Impact:** Vertical waste (hurts Orchestrator chat viewport).  
**Fix:** One owner — either compact PageFrame (eyebrow + modes only) or drop topbar page title on framed pages.

### P4 — Med — Notifications missing from sidebar
**Evidence:** `src/lib/nav.ts` has no `/notifications`; topbar bell links to it.  
**Fix:** Add under System group.

### P5 — Med — Hardcoded hex + `cyan` dead name
**Evidence:** `#F7A600`, `#FFCE6E`, `#080D19`; `Button variant="cyan"` on auth / RequireAuth.  
**Fix:** Tokens only; rename variant to `brand` / `primary`.

### P6 — Med — Sparse accessibility
**Evidence:** `aria-` / `role=` concentrated in orchestrator + auth; trading panels mostly visual.  
**Fix:** Label status badges, form controls, live regions for streams; ensure focus on custom chips.

### P7 — Med — Orchestrator chat height fragility
**Evidence:** `h-[calc(100svh-9rem)]` + AppShell `chatFillPage` branch. Layout works but is brittle to chrome changes.  
**Fix:** Prefer pure flex chain (`min-h-0 flex-1`) end-to-end; keep calc as fallback only.

### P8 — Low — Unused legacy shells
**Evidence:** `PageHeader.tsx`, `SiteNav.tsx` unused; `.sky-hero-glow` naming leftover.  
**Fix:** Delete or rehome; rename glow utility.

### P9 — Low — Magic UI motion budget uneven
**Evidence:** Markets/landing dense with beams/tickers; settings quiet.  
**Fix:** Document when Magic UI is allowed (hero vs data panels).

---

## What is working

1. **Orchestrator chat-first UX** — sticky composer, thread-only scroll, structured `OrchestratorReply` cards, paper/live locks visible.  
2. **Token foundation** — CSS variables for brand/profit/loss/sidebar; fonts (Plus Jakarta + IBM Plex Mono); theme persistence.  
3. **Auth + landing** — coherent orange intent, independent of AppShell.  
4. **Mode badges / paper locks** — safety messaging is consistently present on framed pages.

---

## Migration hotspots (ordered)

1. `app/markets/page.tsx`  
2. `components/WalletBalancePanel.tsx` + `PositionsOrdersPanel.tsx`  
3. `app/news/NewsDashboard.tsx`  
4. `app/backtesting/BacktestingDashboard.tsx` (+ `RunBacktestPanel`)  
5. `features/agent-studio/**`  
6. `components/layout/AppShell.tsx` badge classes  
7. Auth `variant="cyan"` rename  

---

## Recommended sequence

1. **Theme purge** — white/* → semantic tokens; fix rose-100 / white badge text.  
2. **Chrome unify** — single title owner; add Notifications to nav; compact Orchestrator header.  
3. **Hotspot migrate** — markets → panels → news → backtesting → studio.  
4. **A11y pass** — status, forms, focus, live regions.  
5. **Debt cleanup** — cyan rename, delete unused shells, motion budget doc.

---

## Out of scope / not audited in depth

- Visual pixel QA in every breakpoint (spot-checked Orchestrator from screenshots)  
- Performance (bundle / LCP)  
- Backend API contract correctness beyond UI consumption  

---

## Related implementation docs

- Orchestrator / OpenAI readiness reports under `docs/implementation/`  
- UI redesign work landed in `apps/web` (Bybit tokens, Orchestrator chat, Reply cards)
