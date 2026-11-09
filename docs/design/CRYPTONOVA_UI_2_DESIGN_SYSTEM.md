# CryptoNova UI 2.0 Design System

## Brand

- **Name:** CryptoNova  
- **Tagline:** Intelligent Trading. Disciplined Execution.  
- **Accent:** Warm amber `#F7A600` (`--primary` / `--brand`)  
- **Feel:** Institutional trading terminal + AI agent workspace — credible, dense, professional  

## Color tokens

Semantic CSS variables in `apps/web/src/app/globals.css`:

| Token | Role |
|-------|------|
| `--background` / `--foreground` | App canvas + text |
| `--card` / `--muted` / `--border` | Surfaces |
| `--primary` / `--brand` | CTAs and accent |
| `--profit` / `--loss` / `--warning` / `--info` | Trading semantics |
| `--paper-mode` / `--live-mode` / `--halted` / `--stale-data` / `--disabled` | Execution & data state |
| `--chart-1`…`--chart-5` | Chart series |
| `--sidebar-*` | Navigation chrome |

**Theme model:** `:root` = dark charcoal (design-first). `.light` = full light overrides. Default persisted preference remains **light** (`cryptonova.theme.v2`).

Do **not** use `text-white/*`, `border-white/*`, or `bg-white/*` in shared workspace components.

## Typography

- **Plus Jakarta Sans** — UI, nav, headings  
- **IBM Plex Mono** — prices, PnL, timestamps (`tabular-nums` via `MetricValue`)  

Avoid oversized dashboard H1s; prefer compact `AppPageHeader` / `PageFrame`.

## Density

- `comfortable` (default) / `compact`  
- Persisted as `cryptonova.density.v1`  
- Applied as `data-density` on `<html>`

## Components

Primary: shadcn/ui under `components/ui/`.  
Design-system wrappers: `components/design-system/` (`AppPageHeader`, `PageSection`, `StatCard`, `StatusBadge`, `ModeIndicator`, `RiskIndicator`, `EmptyState`, `ErrorState`, `LoadingState`, `DataFreshnessBadge`, `MetricValue`).  
Magic UI: landing + orchestrator welcome only — respect `prefers-reduced-motion`.  
AI Elements: orchestrator chat patterns; no fabricated reasoning.

## Status conventions

| State | Visual |
|-------|--------|
| PAPER | `StatusBadge` tone `paper` |
| LIVE locked | tone `live` / ModeBadge `live-locked` |
| Halted | tone `halted` |
| Stale data | tone `stale` + freshness badge |
| Risk blocked | `RiskIndicator` + exact backend reason text |

Always pair color with a text label.

## Accessibility

Target WCAG 2.2 AA where applicable: keyboard nav, focus rings, labeled forms, live regions for meaningful (not high-frequency tick) updates, reduced motion.

## Animation budget

Allowed: landing hero, orchestrator empty state, infrequent connection success.  
Forbidden: animating every price tick, continuous risk warning pulse, order-table shimmer.
