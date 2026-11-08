"""
News service singleton (Prompt 69A.1).

Runtime uses Supabase PostgreSQL only (fail closed).
In-memory repository is allowed solely via ``reset_news_service_for_tests``.
"""

from __future__ import annotations

import threading

from agent.news.config import NewsConfig
from agent.news.repository import InMemoryNewsRepository
from agent.news.service import NewsIntelligenceService
from apps.api.app.news.pg_repository import NewsStorageError, PostgresNewsRepository
from apps.api.app.news.unavailable_repository import UnavailableNewsRepository

_LOCK = threading.Lock()
_SERVICE: NewsIntelligenceService | None = None


def _build_runtime_service(config: NewsConfig | None = None) -> NewsIntelligenceService:
    cfg = config or NewsConfig.from_env()
    try:
        from apps.api.app.db import create_db_engine

        engine = create_db_engine()
        from apps.api.app.news.alert_pg import PostgresAlertRepository

        repo = PostgresNewsRepository(engine)
        alert_repo = PostgresAlertRepository(engine)
        if not repo.ping():
            reason = (
                "storage_unavailable: app.news_* tables missing or DATABASE_URL unreachable. "
                "Apply Alembic revision 20261108_0007 on the development target first."
            )
            return NewsIntelligenceService(
                UnavailableNewsRepository(reason),
                config=cfg,
                storage_error=reason,
            )
        return NewsIntelligenceService(
            repo, config=cfg, storage_error=None, alert_repo=alert_repo
        )
    except NewsStorageError as exc:
        reason = f"{exc.code}:{exc.message}"
        return NewsIntelligenceService(
            UnavailableNewsRepository(reason),
            config=cfg,
            storage_error=reason,
        )
    except Exception as exc:  # noqa: BLE001
        reason = f"storage_unavailable:{exc}"
        return NewsIntelligenceService(
            UnavailableNewsRepository(reason),
            config=cfg,
            storage_error=reason,
        )


def get_news_service(config: NewsConfig | None = None) -> NewsIntelligenceService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = _build_runtime_service(config)
        elif config is not None:
            _SERVICE.config = config
        kind = getattr(_SERVICE.repo, "storage_kind", lambda: "")()
        if (
            kind == "memory_test_only"
            and not getattr(_SERVICE, "_allow_memory_for_tests", False)
        ):
            _SERVICE.storage_error = (
                "storage_misconfigured: in-memory news repository is not allowed at runtime"
            )
        return _SERVICE


def reset_news_service_for_tests(service: NewsIntelligenceService | None = None) -> None:
    """Test hook — may inject InMemoryNewsRepository."""
    global _SERVICE
    with _LOCK:
        if service is not None and isinstance(service.repo, InMemoryNewsRepository):
            setattr(service, "_allow_memory_for_tests", True)
        _SERVICE = service
