# Telegram Notification Contract (69B)

Default: **off**.

```dotenv
NEWS_ALERTS_ENABLED=false
NEWS_TELEGRAM_ENABLED=false
NEWS_TELEGRAM_BOT_TOKEN=
NEWS_TELEGRAM_CHAT_ID=
```

Tokens are read from the API environment only. They are not hardcoded, not returned by status, and redacted from delivery errors.

## When a message is sent

- Alert engine created a persisted alert.
- `NEWS_TELEGRAM_ENABLED=true` and both token and chat id are set.
- Preference `telegram_enabled` is not required for the transport to be constructed; missing credentials force `enabled=false` on the adapter.
- In-app alerts still record when Telegram is skipped.

## Message fields

CryptoNova heading, severity, symbol, headline, verification, timestamp, short explanation, source link, and an advisory line that the message does not place orders.

## Delivery rules

| Rule | Behavior |
| --- | --- |
| Timeout | 8 seconds per attempt |
| Retries | At most 3, bounded backoff |
| Idempotency | `telegram:{alert_id}` delivery row; confirmed rows are not re-sent as new confirmations |
| Rate limit | Minimum interval between attempts (default 1s) |
| Confirmation | `status=confirmed` only after HTTP 2xx from Telegram |
| Failure | `status=failed` with redacted error; alert remains in-app |
| Tests | Injected transport only. Automated tests do not call Telegram |

In-app channel status is `recorded`, which is not an external provider confirmation.
