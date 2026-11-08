# News Dashboard Report (69B)

## Surfaces

| Surface | Path | Data |
| --- | --- | --- |
| News page | `/news` | Status, articles, events, alerts, provider health |
| Dashboard strip | `/dashboard` | Unread count from `/api/news/alerts/unread-count` |
| Nav | Sidebar “News” | Real route, no fixture feed |

## Sections

- News feed: title, source, coin hints, publication time, source link
- Critical alerts: severity badge, unread/acknowledged, symbols, headline, timestamps, verification, acknowledge, detail
- Agent health: collection flag, auto-collection flag, storage, alert engine, Telegram, scheduler note
- Filters: BTC / ETH / SOL, severity, category, verification, date range (applied to the loaded page)

## States

`newsViewState` distinguishes loading, disabled (`NEWS_READ_API_ENABLED` off or HTTP 503), error, empty, stale/delayed, and ready. Disabled and empty states do not invent demo alerts.

## Limitation

Filters apply to the current API page (limit 50), not a server-side historical query. Automatic collection remains off, so the page stays empty until an operator runs collection and the read API is enabled.
