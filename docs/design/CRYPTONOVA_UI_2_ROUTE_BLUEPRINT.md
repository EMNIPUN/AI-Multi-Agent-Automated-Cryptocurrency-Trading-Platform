# CryptoNova UI 2.0 Route Blueprint

## Navigation architecture

Source: `apps/web/src/lib/nav.ts` → `AppSidebar` + Ctrl+K `CommandPalette`.

| Group | Route | Label |
|-------|-------|-------|
| AI Command Center | `/dashboard` | Overview |
| | `/orchestrator` | AI Orchestrator |
| | `/agents` | Agent Workspace |
| | `/agents/live` | Live AI Analysis |
| | `/llm` | LLM Intelligence |
| Trading Desk | `/markets` | Markets |
| | `/portfolio` | Portfolio |
| | `/positions` | Positions & Orders |
| | `/paper` | Paper Trading |
| | `/risk` | Risk Center |
| Research | `/news` | News Intelligence |
| | `/strategy` | Strategy Research |
| | `/backtesting` | Backtesting |
| | `/analytics` | Analytics |
| System | `/notifications` | Notifications |
| | `/settings/exchanges` | Exchange Connections |
| | `/settings` | Settings |
| | `/system` | System Health |

Marketing/auth (no AppShell): `/`, `/login`, `/signup`, `/forgot-password`, `/reset-password`.

## Shell layout

```
AppShell
  AppSidebar
  SidebarInset
    AppTopbar (breadcrumb + search + theme/density + user)
    GlobalStatusBar (PAPER / LIVE locked / supervisor)
    main (PageMotion → page)
    footer (hidden on /orchestrator)
```

**Title owner:** content `PageFrame` / `AppPageHeader`. Topbar shows breadcrumbs only.

## Page templates

| Template | Used by |
|----------|---------|
| PageFrame + SectionPanel | settings, risk, agents, strategy, system, … |
| Fill-height chat grid | `/orchestrator` |
| Custom terminal (tokenized) | `/markets`, agent-studio |
| Landing stack | `/` |
| AuthShell | auth routes |

## Orchestrator regions

1. **Left (lg+):** New conversation + client-local session  
2. **Center:** Command chat (sticky composer, `OrchestratorReply`)  
3. **Right (xl+):** Session context, tool trace, agents, paper PnL  

APIs: `GET/POST` `/api/orchestrator/{status,report,chat}` only.

## Data requirements (honest)

- Never merge paper + exchange equity.  
- Never invent agent heartbeats or tool traces.  
- Live analysis = market data analysis ≠ live trading.  
- Risk pages fail closed when private feeds unavailable.

## Responsive

| Width | Behavior |
|-------|----------|
| < lg | Orchestrator: hide left/right rails; New chat chip |
| lg | Left + center |
| xl | Full three-region |
| Mobile | Sidebar drawer; tables scroll horizontally |

## Density

`data-density=comfortable|compact` on `<html>` via Settings + topbar toggle.
