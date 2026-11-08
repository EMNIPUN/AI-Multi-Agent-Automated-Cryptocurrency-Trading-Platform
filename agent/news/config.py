"""News intelligence feature flags and limits (Prompt 69A). All collection gates default OFF."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


NEWS_SCHEMA_VERSION = "69B.0.0"
NEWS_CONTEXT_SCHEMA_VERSION = "69C.1.0"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class NewsConfig:
    """Safe defaults — collection and LLM stay off unless explicitly enabled."""

    collection_enabled: bool = False
    read_api_enabled: bool = False
    alerts_enabled: bool = False  # 69B — kept false in 69A
    llm_enabled: bool = False  # 69D — kept false in 69A
    advisory_enabled: bool = False  # 69C pipeline influence — kept false
    http_timeout_seconds: float = 15.0
    http_max_retries: int = 2
    http_min_interval_seconds: float = 0.25
    max_articles_per_run: int = 100
    max_events_per_context: int = 10
    monitored_symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    newsdata_api_key: str | None = None
    rss_feed_urls: tuple[str, ...] = field(default_factory=tuple)
    telegram_enabled: bool = False
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    auto_collection_enabled: bool = False
    collection_interval_seconds: int = 900
    alert_min_severity: str = "HIGH"
    alert_cooldown_ms: int = 1_800_000
    alert_ttl_ms: int = 21_600_000

    @classmethod
    def from_env(cls) -> "NewsConfig":
        key = (os.environ.get("NEWSDATA_API_KEY") or "").strip() or None
        feeds_raw = (os.environ.get("NEWS_RSS_FEED_URLS") or "").strip()
        feeds = tuple(u.strip() for u in feeds_raw.split(",") if u.strip()) if feeds_raw else ()
        return cls(
            collection_enabled=_env_bool("NEWS_COLLECTION_ENABLED", False),
            read_api_enabled=_env_bool("NEWS_READ_API_ENABLED", False),
            alerts_enabled=_env_bool("NEWS_ALERTS_ENABLED", False),
            llm_enabled=_env_bool("NEWS_LLM_ENABLED", False),
            advisory_enabled=_env_bool("NEWS_AGENT_ADVISORY_ENABLED", False),
            http_timeout_seconds=float(_env_int("NEWS_HTTP_TIMEOUT_SECONDS", 15)),
            http_max_retries=_env_int("NEWS_HTTP_MAX_RETRIES", 2),
            max_articles_per_run=_env_int("NEWS_MAX_ARTICLES_PER_RUN", 100),
            max_events_per_context=_env_int("NEWS_MAX_EVENTS_PER_CONTEXT", 10),
            newsdata_api_key=key,
            rss_feed_urls=feeds,
            telegram_enabled=_env_bool("NEWS_TELEGRAM_ENABLED", False),
            telegram_bot_token=(os.environ.get("NEWS_TELEGRAM_BOT_TOKEN") or "").strip() or None,
            telegram_chat_id=(os.environ.get("NEWS_TELEGRAM_CHAT_ID") or "").strip() or None,
            auto_collection_enabled=_env_bool("NEWS_AUTO_COLLECTION_ENABLED", False),
            collection_interval_seconds=max(60, _env_int("NEWS_COLLECTION_INTERVAL_SECONDS", 900)),
            alert_min_severity=(os.environ.get("NEWS_ALERT_MIN_SEVERITY") or "HIGH").strip().upper() or "HIGH",
            alert_cooldown_ms=_env_int("NEWS_ALERT_COOLDOWN_MS", 1_800_000),
            alert_ttl_ms=_env_int("NEWS_ALERT_TTL_MS", 21_600_000),
        )
