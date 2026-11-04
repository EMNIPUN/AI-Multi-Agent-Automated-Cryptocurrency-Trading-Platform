# Phase 3A — CryptoNova Premium Frontend Foundation

| Field | Value |
|-------|-------|
| Date | 2026-11-04 |
| Project | CryptoNova — Intelligent Trading. Disciplined Execution. |
| Scope | Premium Next.js App Router dashboard foundation |
| `PRIVATE_DATA_READS_ENABLED` | **false** (unchanged) |
| Migration `20261104_0002` | **Not applied** |
| Live trading HTTP | **Disabled** |
| Paper order submit | **Disabled** |

---

## Components and libraries installed

| Library | Role |
|---------|------|
| Next.js 15.1.3 / React 19 | App Router frontend |
| Tailwind CSS 3.4 + `tailwindcss-animate` | Design tokens / utilities |
| shadcn/ui (New York style, hand-wired) | Button, Card, Badge, Tabs, Dialog, Sheet, Table, Input, Label, Select, Tooltip, Skeleton, Dropdown, ScrollArea, Separator |
| Magic UI–style free patterns | `NumberTicker`, `AnimatedList`, `BorderBeam`, `BlurFade` (motion-based; respects `prefers-reduced-motion`) |
| `@xyflow/react` | Agent workflow diagram |
| `lightweight-charts` | Candlesticks |
| `recharts` | Analytics equity curve |
| `lucide-react` | Icons |
| `motion` | Functional transitions |
| `@supabase/supabase-js` | Auth client scaffold only |
| `next-themes` | Theme readiness (dark default) |

Package manager: **npm** (`apps/web/package.json`).

---

## Next.js project structure

```text
apps/web/src/
  app/
    layout.tsx                 # AppShell + dark tokens
    page.tsx                   # redirect → /dashboard
    dashboard/page.tsx
    agents/page.tsx
    agents/live/page.tsx
    markets/page.tsx
    portfolio/page.tsx
    positions/page.tsx
    paper/page.tsx
    risk/page.tsx
    analytics/page.tsx
    settings/page.tsx
    api/exchange/wallet/       # same-origin Bybit wallet proxy
    api/observability/*        # fixture snapshot proxies
  components/
    ui/                        # shadcn primitives
    magicui/                   # selective Magic UI patterns
    layout/AppShell.tsx
    agents/AgentWorkflowFlow.tsx
    shared/*
    CandleChart.tsx, WalletBalancePanel.tsx, …
  lib/
    utils.ts, nav.ts, fixtures/*, observability/*, supabase/client.ts
```

---

## Routes implemented

| Route | Purpose | Data mode |
|-------|---------|-----------|
| `/` | Redirect to dashboard | — |
| `/dashboard` | Equity area, agent/risk cards, activity list, wallet panel | SAMPLE + live wallet if API up |
| `/agents/live` | Command Center + React Flow + chart + orders + timeline | SAMPLE fixtures |
| `/agents` | Agent directory (EMA/RSI ready; SMC/Coordinator soon) | Demo |
| `/markets` | Chart + watchlist placeholders | SAMPLE chart |
| `/portfolio` | Wallet panel + allocation placeholder | Live wallet / unavailable |
| `/positions` | Positions/orders placeholders | Unavailable (honest) |
| `/paper` | Virtual 10k UI, disabled order entry | SAMPLE demo |
| `/risk` | Risk placeholders | Unavailable |
| `/analytics` | SAMPLE equity curve (Recharts) | SAMPLE |
| `/settings` | Auth scaffold + connection health | Demo |

---

## shadcn/ui and Magic UI usage

- **shadcn**: local `components/ui/*` matching New York + CSS variables; `components.json` present for future `shadcn add`.
- **Magic UI**: selective free patterns implemented under `components/magicui/*` (Number Ticker, Animated List, Border Beam, Blur Fade). Not a bulk install of the registry. Pro components not used.
- Animations gated by `prefers-reduced-motion`; no fake ticking prices for showcase.

---

## UI data-source status

| Source | Status |
|--------|--------|
| Observability snapshot/paper | Fixture / SAMPLE via Next proxy → FastAPI |
| Live SSE | Disabled (`403`) |
| Bybit UNIFIED wallet | Read-only FastAPI `/api/v1/exchange/wallet` when enabled |
| Positions / risk / private catalog | Unavailable placeholders |
| Paper broker | Not implemented; submit disabled |

Fixtures are labeled **SAMPLE / DEMO**. No invented live ticker prices on watchlist.

---

## Agent workflow visualization

React Flow graph:

Market Data → Confirmed Candle → Strategy → Signal → Risk → Intent → Execution/Simulation → Reconciliation → Position

- DEMO badge on canvas
- BLOCKED/ACTIVE/DONE states
- Explicit note: **ACCEPTED ≠ FILLED**

---

## Real Bybit integration blockers

1. Operator-local wallet read is not multi-tenant ownership yet.
2. Positions/orders/funding APIs not exposed as owned FastAPI contracts.
3. `PRIVATE_DATA_READS_ENABLED=false`; migration `20261104_0002` not applied.
4. Browser must never receive Bybit secrets (enforced via server proxy).

---

## Paper broker limitations

- Virtual equity UI only
- Order entry disabled
- No durable fills / no Bybit routing

---

## Test / build results (actual)

### Frontend
```text
npm run typecheck     → pass
npm run test:events   → check-events.mjs: ok
npm run build         → Compiled successfully (18 routes)
```
SWC native binary warning on this Windows environment (`next-swc.win32-x64-msvc.node is not a valid Win32 application`) — build still completed via fallback.

`next lint` available via `eslint-config-next` (installed).

### Python
```text
uv run pytest -q
178 passed, 1 warning
```

### Security non-actions
- No migration apply / remote DDL
- No live trading routes
- No secrets printed / no auto commit

---

## Screenshots

Not captured in-agent. Local verify:

```powershell
cd apps/web
npm run dev
# open http://localhost:3000/dashboard
# ensure API: uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

---

## Remaining tasks for Phase 3B

1. Apply/verify ownership migration; then gated private SSE with same-origin auth proxy.
2. Wire AgentRunner observability publisher → live Command Center (no fake RUNNING).
3. Owned Bybit positions/orders read adapters + user↔exchange-account binding.
4. Persistent Python paper broker before enabling submit.
5. Full Supabase Auth UI (login/session) using anon key only.
6. Repair/reinstall Next SWC binary if Windows native warning persists.
7. Expand Vitest/component navigation coverage; optional Playwright smoke.

---

## Success checklist

| Criterion | Status |
|-----------|--------|
| Premium dark fintech shell | Pass |
| shadcn + selective Magic UI | Pass |
| All listed routes | Pass |
| Agent workflow (React Flow) | Pass |
| Charts (Lightweight + Recharts) | Pass |
| Real vs paper visually separated | Pass |
| Fixtures labeled; no fake live fills | Pass |
| Trading remains disabled | Pass |
| Typecheck + production build | Pass |
| Python suite green | **178 passed** |
