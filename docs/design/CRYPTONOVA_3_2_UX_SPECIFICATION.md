# CryptoNova 3.2 — UX specification

Date: 2026-11-15. Builds on the Obsidian Amber foundation (`CRYPTONOVA_3_DESIGN_SYSTEM.md`); tokens, sidebar, topbar and navigation were not changed.

## Operating principle

Every status word on screen is a backend fact. The UI never writes "locked", "off" or "running" from a constant; it reads `/api/automation/status`, `/api/orchestrator/*`, `/api/market/status` and shows what they return — including **LIVE armed · Approve per order** when the API server is armed for mainnet. Unknown stays "Unknown".

## Shared vocabulary

| Component | Rule |
|---|---|
| `StatusIndicator` | One of running / idle / paused / stopped / failed / blocked / unknown / stale / ok. Always icon + text. `normalizeStatus()` maps backend words (ACTIVE, HALTED, ERROR…) onto it. |
| `ExecutionMode` | PAPER · TESTNET off/armed · LIVE locked / LIVE armed · Approve per order. `armed` comes from the server. |
| `FinancialValue` | IBM Plex Mono, tabular. Formats decimal strings without `Number` round-trips (`lib/formatting/decimal.ts`); signed colour only for PnL-style values; unit label in sans. |
| `MetricCard` / `MetricCardGrid` | KPI tiles with explicit `loading` and `muted` (source unavailable) states. |
| `DataFreshness` | Live-ticking age pill; stale after a per-context threshold (candle interval, heartbeat 180 s). |
| `ReasonList` | Plain-language explanation of backend reason codes (`lib/formatting/reason-codes.ts`), raw code kept in mono. |
| `DataTable` | TanStack Table: search, sort (numeric-aware for decimal strings), column visibility, pagination, row selection, `<th scope="col">`, `aria-sort`, horizontal scroll container. |
| `ErrorState` | Human text + machine code + timestamp + retry. |
| `EmptyState` | Guidance, never placeholder numbers. |

## Route intent

| Route | What the person learns first |
|---|---|
| `/dashboard` | Operational status (execution lanes, OpenAI mode, supervisor, risk engine, market data) → KPIs → realized equity + agent activity + current analysis → signals, vetoes, paper activity. |
| `/orchestrator` | Three regions: threads (server `/conversations`), conversation, context inspector (market scope, supervisor, latest analysis, agents, risk, model & spend). Reply footer states OpenAI / LocalPlanner fallback / budget blocked / model unavailable / tool failed / stale / cancelled. Tool trace lists only `result_envelopes` the API returned. |
| `/agents` | Read-only React Flow graph of the real spine (market → analysts → coordinator → risk → paper supervisor → outcome; advisory dashed). Node click → inspector with evidence, reason codes, errors, recent execution timeline. |
| `/agents/live` | Public-candle pipeline evaluation (BTC/ETH/SOL allowlist) with freshness, trend/momentum/regime metrics, strategy and risk verdicts; legacy worker studio collapsed below. |
| `/markets` | Watchlist (search, add, favorite) · chart with timeframe + EMA toggle · order book + summary · technical metrics + agent analysis + tape. |
| `/positions` | One grid for supervisor journal + read-API archive rows, mode/market/status filters, row detail sheet. |
| `/portfolio` | Account-source switch: paper journal vs read-only exchange wallet; never mixed. |
| `/risk` | Global verdict, risk budget, max exposure, loss budgets as progress bars, decision gate reason codes, position-level protection, veto timeline, protective exits. |
| `/autonomy` | Unchanged controls + activity timeline + agent runtime + honest lane badges. |
| `/paper` | Live cockpit (equity, PnL, drawdown, duration, controls with confirm step, latest decision, closed trades grid) + archived read-API sessions tab. |
| `/llm` | Advisory status, spend, comparison report, audit grid. |
| `/system`, `/settings`, `/notifications` | Adapter probes, runtime facts, lanes; notifications from risk/supervisor/news/system facts only. |

## Motion

120–240 ms transitions; `animate-ping` on running dots is suppressed under `motion-reduce`; existing border beams and marquees stop under `prefers-reduced-motion`. Live prices are never animated.

## Responsive

Orchestrator threads and context collapse into sheets below `lg` / `xl`; agent inspector becomes a bottom sheet under 768 px; markets watchlist becomes a left sheet under `lg`; `DataTable` columns declare `hideBelow` and the grid scrolls horizontally inside its own container.
