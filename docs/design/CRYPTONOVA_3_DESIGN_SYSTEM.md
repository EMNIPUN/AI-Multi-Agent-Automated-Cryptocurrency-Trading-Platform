# CryptoNova 3 — Obsidian Amber

Dark is the primary theme. Light mode is a full override of the same tokens. Do not add a second palette.

Brand amber (`#F7A600`) is for primary actions, focus, and the active navigation mark. Profit (`#20C997` / light `#087A54`) and loss (`#EF6674` / light `#B4233D`) are the only colors for signed money. Execution mode is always labeled in text.

## Tokens

Defined once in `apps/web/src/app/globals.css` and exposed through `apps/web/tailwind.config.ts`.

| Role | Dark | Light |
|---|---|---|
| Background | `#090D13` | `#F5F7FA` |
| Sidebar | `#0D131C` | `#FFFFFF` |
| Card | `#121820` | `#FFFFFF` |
| Elevated | `#1A2230` | `#EEF2F7` |
| Border | `#28313D` | `#D9E0EA` |
| Primary text | `#F3F5F8` | `#111827` |
| Secondary text | `#A5AFBD` | `#526175` |
| Brand text | `#F7A600` | `#8B5100` |
| Button fill | `#F7A600` | `#F7A600` |

## Type and density

Plus Jakarta Sans for UI. IBM Plex Mono with tabular numerals for prices, sizes, PnL, and ids. Comfortable and compact density persist in `localStorage` under `cryptonova.density.v1`. Theme persists under `cryptonova.theme.v3`. Missing theme means dark.

## Motion

Border beams and marquees stop under `prefers-reduced-motion`. Do not animate live prices. Low-frequency KPIs may use `NumberTicker`.
