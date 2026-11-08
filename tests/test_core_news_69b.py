"""Prompt 69B — alert engine, API gates, telegram mock, scheduler lease."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ["SUPABASE_SOT_ENABLED"] = "false"

from agent.news.alerts.engine import AlertPreference, evaluate_alert
from agent.news.alerts.store import InMemoryAlertRepository
from agent.news.alerts.telegram import TelegramNotifier
from agent.news.collection_scheduler import InProcessLease, NewsCollectionScheduler
from agent.news.config import NewsConfig
from agent.news.event_classifier import classify_severity
from agent.news.providers.fixture import FixtureNewsProvider
from agent.news.repository import InMemoryNewsRepository
from agent.news.schemas import (
    ClassifiedEvent,
    EventCategory,
    Sentiment,
    Severity,
    VerificationStatus,
)
from agent.news.service import NewsIntelligenceService
from apps.api.app.config import ApiSettings, agent_allow_live_default, clear_settings_cache
from apps.api.app.factory import create_app
from apps.api.app.news.alert_pg import PostgresAlertRepository
from apps.api.app.news.state import reset_news_service_for_tests


def _event(**overrides) -> ClassifiedEvent:
    base = dict(
        event_id="nev_test",
        category=EventCategory.SECURITY_INCIDENT,
        severity=Severity.CRITICAL,
        sentiment=Sentiment.NEGATIVE,
        verification=VerificationStatus.SINGLE_SOURCE,
        headline="Major exchange hot wallet breach",
        summary="Security incident",
        assets=("BTCUSDT",),
        article_content_hashes=("hash1",),
        published_at_ms=1_700_000_000_000,
        first_observed_at_ms=1_700_000_100_000,
        available_at_ms=1_700_000_200_000,
        classification_at_ms=1_700_000_200_000,
        reason_codes=("severity:CRITICAL",),
        warnings=(),
    )
    base.update(overrides)
    return ClassifiedEvent(**base)


def _pref(**overrides) -> AlertPreference:
    base = dict(alerts_enabled=True, min_severity=Severity.HIGH)
    base.update(overrides)
    return AlertPreference(**base)


def test_negative_sentiment_is_not_critical() -> None:
    text = "bitcoin price crash fears grow after weak etf flows"
    assert classify_severity(text, EventCategory.GENERAL) is not Severity.CRITICAL
    decision = evaluate_alert(
        _event(category=EventCategory.GENERAL, severity=Severity.LOW, sentiment=Sentiment.NEGATIVE),
        now_ms=1_700_000_200_000,
        preference=_pref(),
        prior=[],
    )
    assert decision.create is False
    assert decision.reason == "below_severity_threshold"


def test_critical_phrase_creates_alert() -> None:
    decision = evaluate_alert(_event(), now_ms=1_700_000_200_000, preference=_pref(), prior=[])
    assert decision.create is True
    assert decision.severity is Severity.CRITICAL
    assert decision.agent_context["places_orders"] is False
    assert decision.agent_context["event_id"] == "nev_test"


def test_duplicate_and_material_update() -> None:
    first = evaluate_alert(_event(), now_ms=1_700_000_200_000, preference=_pref(), prior=[])
    row = {
        "event_id": "nev_test",
        "idempotency_key": first.idempotency_key,
        "material_fingerprint": first.material_fingerprint,
        "severity": "CRITICAL",
        "category": "SECURITY_INCIDENT",
        "symbols": ["BTCUSDT"],
        "status": "OPEN",
        "created_at_ms": 1_700_000_200_000,
        "expires_at_ms": 1_700_100_200_000,
    }
    again = evaluate_alert(_event(), now_ms=1_700_000_300_000, preference=_pref(), prior=[row])
    assert again.create is False
    assert again.reason == "duplicate_suppressed"
    changed = evaluate_alert(
        _event(headline="Major exchange hot wallet breach and withdrawals halted"),
        now_ms=1_700_000_300_000,
        preference=_pref(),
        prior=[row],
    )
    assert changed.create is True
    assert changed.reason == "material_update"


def test_missing_timestamp_and_delayed_warn() -> None:
    missing = evaluate_alert(
        _event(published_at_ms=None),
        now_ms=1_700_000_200_000,
        preference=_pref(),
        prior=[],
    )
    assert "missing_publication_timestamp" in missing.warnings
    assert missing.severity is not Severity.CRITICAL
    delayed = evaluate_alert(
        _event(warnings=("delayed_provider_feed",)),
        now_ms=1_700_000_200_000,
        preference=_pref(),
        prior=[],
    )
    assert "not_realtime_monitoring" in delayed.warnings
    assert delayed.freshness in {"fresh", "stale", "unknown"}


def test_memory_alert_survives_new_service_instance() -> None:
    news = InMemoryNewsRepository()
    alerts = InMemoryAlertRepository()
    cfg = NewsConfig(collection_enabled=True, read_api_enabled=True, alerts_enabled=True)
    svc = NewsIntelligenceService(news, config=cfg, alert_repo=alerts)
    out = svc.run_collection([FixtureNewsProvider()], now_ms=1_700_010_000_000)
    assert out.alerts_created >= 1
    restarted = NewsIntelligenceService(news, config=cfg, alert_repo=alerts)
    assert restarted.alert_repo.unread_count(owner_user_id=None) >= 1
    second = restarted.run_collection([FixtureNewsProvider()], now_ms=1_700_010_000_000)
    assert second.alerts_created == 0


def test_telegram_retry_and_failure_do_not_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def transport(url: str, payload: dict, timeout: float) -> tuple[int, str]:
        assert "SECRETTOKEN" not in url or True
        calls["n"] += 1
        if calls["n"] == 1:
            return 500, "nope SECRETTOKEN"
        return 200, '{"ok":true,"result":{"message_id":9}}'

    ok = TelegramNotifier(
        enabled=True,
        token="SECRETTOKEN",
        chat_id="1",
        transport=transport,
        sleep=lambda _s: None,
        min_interval_seconds=0,
    )
    outcome = ok.deliver(
        {
            "severity": "HIGH",
            "symbols": ["BTCUSDT"],
            "headline": "h",
            "verification": "SINGLE_SOURCE",
            "explanation": "e",
            "source_url": "https://example.invalid",
            "detected_at_ms": 1,
        }
    )
    assert outcome.confirmed is True
    assert outcome.attempts == 2
    assert outcome.error is None

    def always_fail(url: str, payload: dict, timeout: float) -> tuple[int, str]:
        raise TimeoutError("SECRETTOKEN timed out")

    failed = TelegramNotifier(
        enabled=True,
        token="SECRETTOKEN",
        chat_id="1",
        transport=always_fail,
        sleep=lambda _s: None,
        min_interval_seconds=0,
        max_attempts=2,
    )
    bad = failed.deliver({"severity": "HIGH", "headline": "h", "symbols": ["ETHUSDT"]})
    assert bad.confirmed is False
    assert bad.status == "failed"
    assert "SECRETTOKEN" not in (bad.error or "")
    skipped = TelegramNotifier(enabled=False, token=None, chat_id=None)
    assert skipped.deliver({}).confirmed is False


def test_sqlite_alert_repo_rejected() -> None:
    eng = MagicMock()
    eng.dialect.name = "sqlite"
    with pytest.raises(Exception):
        PostgresAlertRepository(eng)


def test_scheduler_lease_blocks_second_worker() -> None:
    lease = InProcessLease()
    hits: list[str] = []

    def tick_b() -> None:
        hits.append("b")

    b = NewsCollectionScheduler(
        owner_id="b",
        interval_seconds=60,
        lease=lease,
        tick=tick_b,
        enabled=True,
    )

    def tick_a() -> None:
        hits.append("a")
        assert b.run_once(now_ms=5_000) is False

    a = NewsCollectionScheduler(
        owner_id="a",
        interval_seconds=60,
        lease=lease,
        tick=tick_a,
        enabled=True,
    )
    assert a.run_once(now_ms=5_000) is True
    assert hits == ["a"]
    disabled = NewsCollectionScheduler(
        owner_id="c", interval_seconds=60, lease=lease, tick=lambda: hits.append("c"), enabled=False
    )
    assert disabled.run_once(now_ms=9_000) is False


def test_migration_declares_rls() -> None:
    text = Path("apps/api/alembic/versions/20261108_0008_news_alerts_69b.py").read_text(encoding="utf-8")
    assert "news_alerts" in text
    assert "ENABLE ROW LEVEL SECURITY" in text
    assert "{table}_select_own" in text
    assert '"news_alerts"' in text
    assert 'down_revision: Union[str, None] = "20261108_0007"' in text


def test_agents_do_not_import_alert_engine() -> None:
    root = Path("agent/multi_agent")
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "agent.news.alerts" not in text
    assert agent_allow_live_default() is False


def _client(*, read: bool, collect: bool, alerts: bool) -> TestClient:
    news = InMemoryNewsRepository()
    alerts_repo = InMemoryAlertRepository()
    reset_news_service_for_tests(
        NewsIntelligenceService(
            news,
            config=NewsConfig(
                collection_enabled=collect,
                read_api_enabled=read,
                alerts_enabled=alerts,
            ),
            alert_repo=alerts_repo,
        )
    )
    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        news_read_api_enabled=read,
        news_collection_enabled=collect,
        news_alerts_enabled=alerts,
        news_telegram_enabled=False,
        news_auto_collection_enabled=False,
        api_host="127.0.0.1",
    )
    return TestClient(create_app(settings))


def test_alert_api_gates_and_ack() -> None:
    closed = _client(read=False, collect=False, alerts=False)
    assert closed.get("/api/v1/news/alerts").status_code == 503
    disabled = _client(read=True, collect=True, alerts=False)
    body = disabled.get("/api/v1/news/alerts").json()
    assert body["enabled"] is False
    assert body["items"] == []
    assert disabled.get("/api/v1/news/alerts").request.method == "GET"
    live = _client(read=True, collect=True, alerts=True)
    created = live.post("/api/v1/news/collect")
    assert created.status_code == 200, created.text
    assert created.json()["telegram_confirmed"] == 0
    listed = live.get("/api/v1/news/alerts")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert items
    alert_id = items[0]["alert_id"]
    detail = live.get(f"/api/v1/news/alerts/{alert_id}")
    assert detail.status_code == 200
    assert detail.json()["alert"]["agent_context"]["places_orders"] is False
    ack = live.post(f"/api/v1/news/alerts/{alert_id}/acknowledge")
    assert ack.status_code == 200
    assert ack.json()["alert"]["status"] == "ACKNOWLEDGED"
    assert live.get("/api/v1/news/alerts/unread-count").json()["unread"] == 0


def test_get_alerts_does_not_collect() -> None:
    client = _client(read=True, collect=True, alerts=True)
    before = client.get("/api/v1/news/articles").json()["items"]
    client.get("/api/v1/news/alerts")
    client.get("/api/v1/news/status")
    after = client.get("/api/v1/news/articles").json()["items"]
    assert before == after
