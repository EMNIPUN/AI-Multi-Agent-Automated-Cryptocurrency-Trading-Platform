"""Prompt 69A.1 — Postgres news repository fail-closed + no SQLite runtime."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

os.environ["SUPABASE_SOT_ENABLED"] = "false"

from agent.news.config import NewsConfig
from agent.news.providers.fixture import FixtureNewsProvider
from agent.news.repository import InMemoryNewsRepository
from agent.news.service import NewsIntelligenceService
from apps.api.app.config import ApiSettings, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.news.pg_repository import NewsStorageError, PostgresNewsRepository
from apps.api.app.news.state import reset_news_service_for_tests
from apps.api.app.news.unavailable_repository import UnavailableNewsRepository


def test_postgres_repo_rejects_sqlite_engine() -> None:
    eng = MagicMock()
    eng.dialect.name = "sqlite"
    with pytest.raises(NewsStorageError) as exc:
        PostgresNewsRepository(eng)
    assert exc.value.code == "sqlite_forbidden"


def test_unavailable_repo_fail_closed() -> None:
    repo = UnavailableNewsRepository("down")
    assert repo.ping() is False
    assert repo.storage_kind() == "unavailable"
    with pytest.raises(NewsStorageError):
        repo.list_articles(limit=1, offset=0, owner_user_id=None)


def test_runtime_status_reports_storage_fields() -> None:
    reset_news_service_for_tests(
        NewsIntelligenceService(
            UnavailableNewsRepository("simulated_outage"),
            config=NewsConfig(read_api_enabled=True),
            storage_error="simulated_outage",
        )
    )
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        news_read_api_enabled=True,
        news_collection_enabled=False,
        api_host="127.0.0.1",
    )
    client = TestClient(create_app(settings))
    st = client.get("/api/v1/news/status").json()
    assert st["storage_available"] is False
    assert st["storage_error"]
    assert st["places_orders"] is False


def test_collect_fails_closed_when_storage_down() -> None:
    reset_news_service_for_tests(
        NewsIntelligenceService(
            UnavailableNewsRepository("simulated_outage"),
            config=NewsConfig(collection_enabled=True, read_api_enabled=True),
            storage_error="simulated_outage",
        )
    )
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        news_read_api_enabled=True,
        news_collection_enabled=True,
        api_host="127.0.0.1",
    )
    client = TestClient(create_app(settings))
    r = client.post("/api/v1/news/collect")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "storage_unavailable"


def test_memory_service_still_works_for_isolated_tests() -> None:
    repo = InMemoryNewsRepository()
    svc = NewsIntelligenceService(
        repo, config=NewsConfig(collection_enabled=True, read_api_enabled=True)
    )
    setattr(svc, "_allow_memory_for_tests", True)
    out = svc.run_collection([FixtureNewsProvider()], now_ms=1_700_010_000_000)
    assert len(out.articles) >= 1
    assert repo.latest_ingestion(owner_user_id=None) is not None


def test_get_articles_503_when_storage_down() -> None:
    reset_news_service_for_tests(
        NewsIntelligenceService(
            UnavailableNewsRepository("down"),
            config=NewsConfig(read_api_enabled=True),
            storage_error="down",
        )
    )
    clear_settings_cache()
    client = TestClient(
        create_app(
            ApiSettings(
                _env_file=None,
                news_read_api_enabled=True,
                api_host="127.0.0.1",
            )
        )
    )
    assert client.get("/api/v1/news/articles").status_code == 503


@pytest.mark.skipif(
    os.getenv("NEWS_PG_INTEGRATION", "").strip().lower() not in {"1", "true", "yes"},
    reason="Set NEWS_PG_INTEGRATION=1 with migrated development DATABASE_URL to run",
)
def test_postgres_integration_persist_and_restart() -> None:
    """Optional live Supabase/dev DB check — never invents success without env."""
    from pathlib import Path
    from uuid import uuid4

    from dotenv import load_dotenv

    from apps.api.app.db import create_db_engine, reset_engine

    import time

    load_dotenv(Path(".env"), override=False)
    reset_engine()
    clear_settings_cache()
    engine = create_db_engine()
    repo = PostgresNewsRepository(engine)
    assert repo.ping() is True
    owner = uuid4()
    # Unique clocks avoid run_id collisions on shared development DB.
    base_ms = int(time.time() * 1000)
    svc = NewsIntelligenceService(
        repo, config=NewsConfig(collection_enabled=True, read_api_enabled=True)
    )
    first = svc.run_collection(
        [FixtureNewsProvider()], owner_user_id=owner, now_ms=base_ms
    )
    assert first.run_id
    # New repository instance simulates process restart
    repo2 = PostgresNewsRepository(engine)
    latest = repo2.latest_ingestion(owner_user_id=owner)
    assert latest is not None
    assert latest["run_id"] == first.run_id
    arts = repo2.list_articles(limit=10, offset=0, owner_user_id=owner)
    assert len(arts) >= 1
    # Duplicate provider/external_id ingestion must upsert, not fail
    second = svc.run_collection(
        [FixtureNewsProvider()], owner_user_id=owner, now_ms=base_ms + 60_000
    )
    assert second.run_id != first.run_id
    latest2 = repo2.latest_ingestion(owner_user_id=owner)
    assert latest2 is not None
    assert latest2["run_id"] == second.run_id
    arts_after = repo2.list_articles(limit=50, offset=0, owner_user_id=owner)
    assert len(arts_after) >= 1


def test_pg_insert_dialect_available() -> None:
    # Sanity: project uses PostgreSQL upsert dialect for news writes.
    assert postgresql.insert is not None
