# Phase 3B — Advanced Live Agent Studio

| Field | Value |
|-------|-------|
| Date | 2026-11-05 |
| Route | `/agents/live` |
| Scope | Milestones A–D complete; E–F partial; G fail-closed |
| Wallet panel | Preserved |
| `PRIVATE_DATA_READS_ENABLED` | **false** |
| Migration `0002` | **Not applied** |
| SSE | **Disabled** |
| Real orders | **Disabled** |

---

## 1. Repository audit

Existing `/agents/live` was a single page with fixture/worker toggle, React Flow demo graph, chart, order table, and Animated List timeline. Phase 3B Part 1–2 worker telemetry and order lifecycle observers exist on the Python side. Frontend did not yet present an explainability studio.

TanStack Query was **not** added; polling uses a dedicated hook with visibility-aware intervals to avoid a new dependency.

## 2. Architecture

```text
app/agents/live/page.tsx
  └─ features/agent-studio/components/AgentStudio.tsx
       ├─ AgentStudioHeader
       ├─ ReplayControls
       ├─ WalletBalancePanel (unchanged)
       ├─ StudioWorkflow (React Flow + custom nodes)
       ├─ DecisionInspector (“Why This Decision?”)
       ├─ CandleChart
       ├─ Order lifecycle table
       └─ EventTimelinePanel
hooks/
  use-agent-snapshot.ts   # LIVE/SAMPLE polling; no silent SAMPLE fallback on LIVE
  use-replay-state.ts     # Client-side historical reconstruction
lib/
  workflow-projector.ts   # Evidence → stage states / status labels
  time-formatters.ts
```

## 3. Components added / modified

| Path | Role |
|------|------|
| `features/agent-studio/**` | New Agent Studio feature module |
| `app/agents/live/page.tsx` | Thin wrapper → `<AgentStudio />` |

Preserved: wallet proxy/panel, nav, observability API contracts, SAMPLE/LIVE separation.

## 4. Motion / Magic UI

- `motion/react` for status badge, inspector, and event entrance (respects `useReducedMotion`)
- `BlurFade` page entrance
- `BorderBeam` only on ACTIVE evidenced workflow nodes
- `AnimatedList` for genuine event rows
- No continuous fake analysis animation

## 5. State machine / workflow projection

Stages: Market → Candle → Analysis → Signal → Risk → Intent → Execution → Reconciliation → Position.

Node states: IDLE / ACTIVE / COMPLETED / BLOCKED / FAILED / HALTED / UNKNOWN / UNAVAILABLE.

Rules:

- RUNNING heartbeat alone is not ANALYZING
- HOLD is not a trade
- BLOCKED/HALTED require matching events or authoritative snapshot fields
- `data_mode=unavailable` forces UNAVAILABLE stages
- Order stages stay empty until order.* evidence exists

## 6. Explainability

“Why This Decision?” sections: market context, indicators, strategy conditions (honest NOT EVALUATED when per-rule bits are absent), signal, risk, execution.

Simple vs Advanced mode (persisted in `localStorage` key `cryptonova.agentStudio.explainMode`). Same data; presentation only.

## 7. Timeline, chart, replay

- Timeline: category filters, search, select → jump to workflow stage, copy event id, pause auto-follow
- Chart: existing Lightweight Charts; shows limitation when candle series empty
- Replay: play/pause/prev/next/scrubber/speed; REPLAY banner; does not call trading systems; gap warning when empty

## 8. Actual vs SAMPLE

| Mode | Behavior |
|------|----------|
| LIVE | Polls `source=worker`; rejects fixture payload as leak; unavailable stays empty of SAMPLE |
| SAMPLE | Explicit selector only |
| REPLAY | Reconstructs from last loaded snapshot events |

## 9. Authorization limits

Worker telemetry remains operator-local / fail-closed on the API. Browser JWT still does not unlock private streams. Host-header trust was not loosened.

## 10. Responsive / a11y

- Desktop split: workflow + inspector
- Mobile tabs: Overview / Flow / Chart / Events / Why
- Keyboard stage chips, focus rings, aria labels on selects/scrubber
- Reduced motion supported

## 11. Test / build results

```text
uv run pytest -q
204 passed, 1 warning

apps/web npm run typecheck → pass
apps/web npm run lint → No ESLint warnings or errors (SWC Win32 warning)
apps/web npm run test:events → ok
apps/web vitest agent-studio → 5 passed
apps/web npm run build → Compiled successfully (exit 0)
```

## 12. Screenshots

Not embedded in-agent. Open `http://localhost:3000/agents/live` with `npm run dev`.

## 13. Remaining work

- Milestone E: deeper event↔candle crosshair correlation when live candle series are owned
- Milestone F polish: virtualize very large timelines; persist replay bookmarks
- Milestone G: authenticated owner-scoped telemetry (blocked on ownership migration)
- Export per-rule PASS/FAIL bits from the worker for richer strategy conditions
- Optional TanStack Query once multi-query caching is needed

## Success check

Users can open `/agents/live` and see agent health, market/indicators when evidenced, BUY/SELL/HOLD with reasons, risk verdicts, order evidence when present, and inspect earlier cycles via timeline/replay — without SAMPLE being sold as LIVE and without enabling real trading.
