"""Process owner for optional news polling. Default off."""

from __future__ import annotations

import uuid

from apps.api.app.config import ApiSettings

_SCHEDULER = None


def scheduler_status() -> dict:
    if _SCHEDULER is None:
        return {
            "enabled": False,
            "running": False,
            "last_error": None,
            "note": (
                "Manual collection only. NEWS_AUTO_COLLECTION_ENABLED is false. "
                "Feeds are not realtime."
            ),
        }
    status = _SCHEDULER.status
    return {
        "enabled": status.enabled,
        "running": status.running,
        "last_tick_ms": status.last_tick_ms,
        "last_error": status.last_error,
        "ticks": status.ticks,
        "note": status.note,
    }


def maybe_start_news_scheduler(settings: ApiSettings) -> None:
    global _SCHEDULER
    if not settings.news_auto_collection_enabled or _SCHEDULER is not None:
        return
    from agent.news.collection_scheduler import NewsCollectionScheduler
    from apps.api.app.news.state import get_news_service

    class _DbLease:
        def try_acquire(self, owner_id: str, *, now_ms: int, ttl_ms: int) -> bool:
            repo = getattr(get_news_service(), "alert_repo", None)
            if repo is None or not repo.alerts_ready():
                return False
            acquire = getattr(repo, "try_acquire_collection_lease", None)
            if not callable(acquire):
                return False
            return bool(acquire(owner_id, now_ms=now_ms, ttl_ms=ttl_ms))

        def release(self, owner_id: str) -> None:
            repo = getattr(get_news_service(), "alert_repo", None)
            release = getattr(repo, "release_collection_lease", None)
            if callable(release):
                release(owner_id, now_ms=0)

    def _tick() -> None:
        svc = get_news_service()
        if not svc.config.collection_enabled or not svc.storage_available:
            raise RuntimeError("collection_not_runnable")
        svc.run_collection()

    _SCHEDULER = NewsCollectionScheduler(
        owner_id=f"news-{uuid.uuid4().hex[:8]}",
        interval_seconds=max(60, int(settings.news_collection_interval_seconds or 900)),
        lease=_DbLease(),
        tick=_tick,
        enabled=True,
    )
    _SCHEDULER.start()


def shutdown_news_scheduler() -> None:
    global _SCHEDULER
    if _SCHEDULER is not None:
        _SCHEDULER.stop()
        _SCHEDULER = None
