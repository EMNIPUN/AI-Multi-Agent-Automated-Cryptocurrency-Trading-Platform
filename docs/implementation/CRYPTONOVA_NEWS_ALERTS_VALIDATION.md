# CryptoNova — News Alerts Validation

**Status: IMPLEMENTED BUT UNVERIFIED for the signed-in dashboard. Persistence was verified.**

Development tables `news_alerts`, `news_alert_deliveries`, `news_alert_preferences`, and `news_collection_lease` exist. After the 70B.1 isolated test, alert rows were removed. The current count is 0. That is an empty real table, not demo data.

Verified earlier on this database, with a unique test owner:

- One alert row for a duplicate idempotency key
- Acknowledgement persisted
- Delivery row stored without a provider message id
- Collection lease SQL updates only an expired lease or the same owner

`NEWS_ALERTS_ENABLED`, `NEWS_TELEGRAM_ENABLED`, and `NEWS_AUTO_COLLECTION_ENABLED` stay unset and default to false. No Telegram message was sent. No automatic collection was started.

`/news` redirects unsigned visitors to sign-in. The page code reads `/api/news/alerts` and shows an empty state when the engine is off. That signed-in empty state was not clicked.

The ten news events stored before revision archiving are not alerts and were not rewritten.
