# Phase 3C Part 6A — Exchange Accounts UI

| Field | Value |
|-------|-------|
| Date | 2026-11-06 |
| Route | `/settings/exchanges` |
| Design | CryptoNova dark dashboard (existing Card / Badge / DataModeBanner) |

---

## Features

| UI element | Behavior |
|------------|----------|
| Auth E2E banner | Explicit **Authentication verification required** / Auth E2E NOT PASS |
| Exchange | Bybit |
| Environment | Testnet default; Mainnet button disabled / locked |
| Binding status | pending / active / revoked / error badges |
| Credential ref | Alias only (`pending:bybit-testnet` or `env:…`) |
| Last verified | Shown as Never until activation workflow exists |
| Revoke | Owner-only via proxied POST |
| Live label | Fixture rows show **Not a live connection** — never “connected LIVE” |

---

## Wiring

| Layer | Path |
|-------|------|
| Page | `apps/web/src/app/settings/exchanges/page.tsx` |
| Proxies | `apps/web/src/app/api/exchange/bindings/**` |
| Nav | Settings → Exchanges |
| Settings link | “Manage exchange accounts” |

Bearer tokens from `authHeaders()` only. Break-glass remains disabled for binding routes.

---

## Security UX

- No form fields for Bybit API key / secret.
- Pending request does not imply connected exchange.
- Private wallet reads called out as still off.
