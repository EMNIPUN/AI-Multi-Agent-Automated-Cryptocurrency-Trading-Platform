"""High-level news ingestion service (Prompt 69A / 69A.1)."""

from __future__ import annotations

import time
from typing import Any, Sequence
from uuid import UUID

from agent.news.alerts.engine import AlertPreference, alert_row_from_decision, evaluate_alert
from agent.news.collector import CollectionResult, collect_news
from agent.news.config import NEWS_SCHEMA_VERSION, NewsConfig
from agent.news.context_provider import build_news_context
from agent.news.providers.base import NewsProvider
from agent.news.providers.fixture import FixtureNewsProvider
from agent.news.providers.newsdata import NewsDataProvider
from agent.news.providers.rss import RssNewsProvider
from agent.news.repository import NewsRepository
from agent.news.schemas import Severity


def build_default_providers(config: NewsConfig) -> list[NewsProvider]:
    providers: list[NewsProvider] = []
    if config.rss_feed_urls:
        providers.append(
            RssNewsProvider(
                config.rss_feed_urls,
                timeout=config.http_timeout_seconds,
                delayed=True,
            )
        )
    if config.newsdata_api_key:
        providers.append(
            NewsDataProvider(
                config.newsdata_api_key,
                timeout=config.http_timeout_seconds,
            )
        )
    if not providers:
        providers.append(FixtureNewsProvider())
    return providers


class NewsIntelligenceService:
    def __init__(
        self,
        repo: NewsRepository,
        *,
        config: NewsConfig | None = None,
        storage_error: str | None = None,
        alert_repo: Any | None = None,
        telegram: Any | None = None,
    ) -> None:
        # Runtime must pass an explicit repo (Postgres). Tests may pass InMemory.
        self.repo = repo
        self.config = config or NewsConfig.from_env()
        self.storage_error = storage_error
        self.alert_repo = alert_repo
        self.telegram = telegram

    @property
    def storage_available(self) -> bool:
        if self.storage_error:
            return False
        try:
            return bool(self.repo.ping())
        except Exception:  # noqa: BLE001
            return False

    def run_collection(
        self,
        providers: Sequence[NewsProvider] | None = None,
        *,
        owner_user_id: UUID | None = None,
        now_ms: int | None = None,
    ) -> CollectionResult:
        if not self.storage_available:
            raise RuntimeError(
                self.storage_error
                or "news_storage_unavailable: cannot persist collection to Supabase"
            )
        cfg = self.config
        providers = list(providers) if providers is not None else build_default_providers(cfg)
        result = collect_news(providers, config=cfg, now_ms=now_ms)

        health_rows = [
            {
                "provider_id": pid,
                "ok": not any(pid in e for e in result.errors),
                "checked_ms": result.finished_ms,
                "error": next((e for e in result.errors if e.startswith(pid)), None),
            }
            for pid in result.provider_ids
        ]
        run_payload = {
            "run_id": result.run_id,
            "started_ms": result.started_ms,
            "finished_ms": result.finished_ms,
            "article_count": len(result.articles),
            "event_count": len(result.events),
            "rejected": result.rejected,
            "duplicates_dropped": result.duplicates_dropped,
            "errors": list(result.errors),
            "provider_ids": list(result.provider_ids),
            "schema_version": NEWS_SCHEMA_VERSION,
        }

        persist = getattr(self.repo, "persist_collection", None)
        try:
            if callable(persist):
                persist(
                    provider_ids=list(result.provider_ids),
                    articles=list(result.articles),
                    events=list(result.events),
                    health_rows=health_rows,
                    run_payload=run_payload,
                    owner_user_id=owner_user_id,
                )
            else:
                for pid in result.provider_ids:
                    self.repo.upsert_source(
                        provider_id=pid,
                        name=pid,
                        kind="provider",
                        meta={"schema": NEWS_SCHEMA_VERSION},
                    )
                for h in health_rows:
                    self.repo.record_provider_health(h, owner_user_id=owner_user_id)
                for article in result.articles:
                    self.repo.upsert_article(article, owner_user_id=owner_user_id)
                for event in result.events:
                    self.repo.upsert_event(event, owner_user_id=owner_user_id)
                self.repo.record_ingestion_run(run_payload, owner_user_id=owner_user_id)
        except Exception as exc:  # noqa: BLE001 — do not claim success
            result.errors.append(f"persist_failed:{exc}")
            raise RuntimeError(f"collection_not_persisted:{exc}") from exc
        self._persist_alerts(result, owner_user_id=owner_user_id, now_ms=result.started_ms)
        return result

    def _preference(self, owner_user_id: UUID | None) -> AlertPreference:
        stored: dict[str, Any] | None = None
        if self.alert_repo is not None and self.alert_repo.alerts_ready():
            try:
                stored = self.alert_repo.get_preferences(owner_user_id=owner_user_id)
            except Exception:  # noqa: BLE001
                stored = None
        raw_sev = str((stored or {}).get("min_severity") or self.config.alert_min_severity)
        try:
            min_severity = Severity(raw_sev)
        except ValueError:
            min_severity = Severity.HIGH
        symbols = tuple(str(s) for s in ((stored or {}).get("symbols") or []))
        return AlertPreference(
            alerts_enabled=self.config.alerts_enabled,
            min_severity=min_severity,
            symbols=symbols,
            cooldown_ms=int((stored or {}).get("cooldown_ms") or self.config.alert_cooldown_ms),
            ttl_ms=int((stored or {}).get("ttl_ms") or self.config.alert_ttl_ms),
            in_app_enabled=bool((stored or {}).get("in_app_enabled", True)),
            telegram_enabled=bool((stored or {}).get("telegram_enabled", False)),
        )

    def _source_url(self, event: Any, articles: Sequence[Any]) -> str | None:
        wanted = set(event.article_content_hashes)
        for article in articles:
            if article.content_hash in wanted:
                return article.url
        return None

    def _persist_alerts(
        self,
        result: CollectionResult,
        *,
        owner_user_id: UUID | None,
        now_ms: int,
    ) -> None:
        if not self.config.alerts_enabled:
            return
        if self.alert_repo is None or not self.alert_repo.alerts_ready():
            raise RuntimeError(
                "alerts_schema_unavailable: cannot persist alerts (migration 20261108_0008 required)"
            )
        preference = self._preference(owner_user_id)
        prior = self.alert_repo.list_alerts(limit=500, offset=0, owner_user_id=owner_user_id)
        rows: list[dict[str, Any]] = []
        suppressed = 0
        for event in result.events:
            source_url = self._source_url(event, result.articles)
            decision = evaluate_alert(
                event,
                now_ms=now_ms,
                preference=preference,
                prior=prior + rows,
                source_url=source_url,
            )
            if not decision.create:
                suppressed += 1
                continue
            rows.append(
                alert_row_from_decision(
                    event,
                    decision,
                    now_ms=now_ms,
                    owner_user_id=str(owner_user_id) if owner_user_id else None,
                    source_url=source_url,
                    ttl_ms=preference.ttl_ms,
                )
            )
        try:
            if rows:
                self.alert_repo.upsert_alerts(rows)
            confirmed = self._dispatch_notifications(rows, owner_user_id=owner_user_id, now_ms=now_ms)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"alerts_not_persisted:{exc}") from exc
        result.alerts_created = len(rows)
        result.alerts_suppressed = suppressed
        result.telegram_confirmed = confirmed

    def _dispatch_notifications(
        self,
        rows: list[dict[str, Any]],
        *,
        owner_user_id: UUID | None,
        now_ms: int,
    ) -> int:
        confirmed = 0
        for row in rows:
            self.alert_repo.record_delivery(
                {
                    "delivery_id": f"nad_inapp_{row['alert_id']}",
                    "alert_id": row["alert_id"],
                    "owner_user_id": owner_user_id,
                    "channel": "in_app",
                    "status": "recorded",
                    "attempt_count": 1,
                    "provider_message_id": None,
                    "confirmed_at_ms": None,
                    "last_error": None,
                    "idempotency_key": f"in_app:{row['alert_id']}",
                    "created_at_ms": now_ms,
                    "updated_at_ms": now_ms,
                }
            )
            notifier = self.telegram
            if notifier is None or not getattr(notifier, "enabled", False):
                continue
            outcome = notifier.deliver(row)
            self.alert_repo.record_delivery(
                {
                    "delivery_id": f"nad_tg_{row['alert_id']}",
                    "alert_id": row["alert_id"],
                    "owner_user_id": owner_user_id,
                    "channel": "telegram",
                    "status": outcome.status,
                    "attempt_count": outcome.attempts,
                    "provider_message_id": outcome.provider_message_id,
                    "confirmed_at_ms": now_ms if outcome.confirmed else None,
                    "last_error": outcome.error,
                    "idempotency_key": f"telegram:{row['alert_id']}",
                    "created_at_ms": now_ms,
                    "updated_at_ms": now_ms,
                }
            )
            if outcome.confirmed:
                confirmed += 1
        return confirmed

    def status(self, *, owner_user_id: UUID | None = None) -> dict[str, Any]:
        latest = None
        storage_ok = self.storage_available
        if storage_ok:
            try:
                latest = self.repo.latest_ingestion(owner_user_id=owner_user_id)
            except Exception as exc:  # noqa: BLE001
                storage_ok = False
                self.storage_error = f"storage_read_failed:{exc}"
        return {
            "schema_version": NEWS_SCHEMA_VERSION,
            "collection_enabled": self.config.collection_enabled,
            "read_api_enabled": self.config.read_api_enabled,
            "alerts_enabled": self.config.alerts_enabled,
            "llm_enabled": self.config.llm_enabled,
            "advisory_enabled": self.config.advisory_enabled,
            "auto_collection_enabled": self.config.auto_collection_enabled,
            "alert_engine_enabled": self.config.alerts_enabled,
            "telegram_enabled": bool(
                self.config.telegram_enabled
                and self.config.telegram_bot_token
                and self.config.telegram_chat_id
            ),
            "agent_allow_live": False,
            "storage_kind": getattr(self.repo, "storage_kind", lambda: "unknown")(),
            "storage_available": storage_ok,
            "storage_error": None if storage_ok else (self.storage_error or "storage_unavailable"),
            "latest_ingestion": latest,
            "note": (
                "69A.1 — advisory news on Supabase PostgreSQL only. "
                "Does not change trading decisions or place orders."
            ),
        }

    def context_for_symbol(self, symbol: str, *, owner_user_id: UUID | None = None) -> dict:
        if not self.storage_available:
            return {
                "symbol": symbol.upper(),
                "as_of": "",
                "events": [],
                "context_status": "ERROR",
                "schema_version": "1.0.0",
                "warnings": ["news_storage_unavailable"],
            }
        ctx = build_news_context(
            self.repo,
            symbol=symbol,
            as_of_ms=int(time.time() * 1000),
            config=self.config,
            owner_user_id=owner_user_id,
        )
        return ctx.to_dict()
