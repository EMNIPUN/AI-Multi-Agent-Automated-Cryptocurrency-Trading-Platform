"""Prompt 69C — advisory NewsContext. Decisions stay identical."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SUPABASE_SOT_ENABLED", "false")

from agent.multi_agent.config import PaperRiskConfig, SignalPipelineConfig
from agent.multi_agent.fixtures import bullish_trend_closes, make_series, series_now_ms
from agent.multi_agent.pipeline import SignalPipeline
from agent.multi_agent.risk_agent import SignalRiskState
from agent.news.context_provider import build_news_context
from agent.news.config import NewsConfig
from agent.news.repository import InMemoryNewsRepository
from agent.news.schemas import ClassifiedEvent, ContextStatus, EventCategory, Sentiment, Severity, VerificationStatus
from apps.api.app.config import agent_allow_live_default


class _Repo:
    def __init__(self, events: list[dict], fail: bool = False) -> None:
        self.events = events
        self.fail = fail

    def list_events_for_symbol(self, symbol: str, *, limit: int, owner_user_id) -> list[dict]:
        if self.fail:
            raise RuntimeError("postgres down")
        rows = [e for e in self.events if symbol in e.get("assets", [])]
        return rows[:limit]

    def latest_ingestion(self, *, owner_user_id):
        return {"run_id": "r"} if self.events else None


def _row(**overrides) -> dict:
    base = {
        "event_id": "nev_a",
        "category": "SECURITY_INCIDENT",
        "severity": "HIGH",
        "sentiment": "NEGATIVE",
        "verification": "SINGLE_SOURCE",
        "headline": "Exchange issue",
        "summary": "Exchange issue",
        "assets": ["BTCUSDT"],
        "article_content_hashes": ["h1"],
        "published_at_ms": 1_000,
        "first_observed_at_ms": 5_000,
        "available_at_ms": 5_000,
        "classification_at_ms": 5_000,
        "warnings": [],
        "source_url": "https://example.invalid/a",
    }
    base.update(overrides)
    return base


def _pipe() -> SignalPipeline:
    return SignalPipeline(
        config=SignalPipelineConfig(risk=PaperRiskConfig(), min_confirmed_bars=210),
        risk_state=SignalRiskState(),
    )


def test_context_schema_and_symbol_filter() -> None:
    repo = _Repo([_row(), _row(event_id="nev_eth", assets=["ETHUSDT"])])
    ctx = build_news_context(repo, symbol="BTCUSDT", as_of_ms=10_000, config=NewsConfig())
    body = ctx.to_dict()
    assert body["sentiment_is_not_a_trade_signal"] is True
    assert body["source_event_ids"] == ["nev_a"]
    assert body["revision_history_available"] is False
    assert "revision_snapshots_unavailable" in body["warnings"]
    assert body["context_hash"]


def test_publication_versus_first_available_and_future_exclusion() -> None:
    repo = _Repo([_row(published_at_ms=1_000, available_at_ms=8_000, classification_at_ms=8_000)])
    early = build_news_context(repo, symbol="BTCUSDT", as_of_ms=3_000, config=NewsConfig())
    assert early.events == ()
    assert early.context_status is ContextStatus.UNAVAILABLE
    later = build_news_context(repo, symbol="BTCUSDT", as_of_ms=8_000, config=NewsConfig())
    assert [e.event_id for e in later.events] == ["nev_a"]


def test_future_revision_excluded_because_history_is_not_stored() -> None:
    repo = _Repo([_row(available_at_ms=1_000, classification_at_ms=9_000)])
    ctx = build_news_context(repo, symbol="BTCUSDT", as_of_ms=2_000, config=NewsConfig())
    assert ctx.events == ()
    assert "future_events_excluded" in ctx.warnings
    assert ctx.revision_history_available is False


def test_delayed_stale_missing_and_storage_down() -> None:
    delayed = build_news_context(
        _Repo([_row(warnings=["delayed_provider_feed"])]),
        symbol="BTCUSDT",
        as_of_ms=6_000,
        config=NewsConfig(),
    )
    assert delayed.delayed_provider is True
    stale = build_news_context(
        _Repo([_row(available_at_ms=1_000)]),
        symbol="BTCUSDT",
        as_of_ms=1_000 + 7 * 60 * 60 * 1000,
        config=NewsConfig(),
    )
    assert stale.context_status is ContextStatus.STALE
    missing = build_news_context(_Repo([]), symbol="BTCUSDT", as_of_ms=5_000, config=NewsConfig())
    assert missing.context_status is ContextStatus.UNAVAILABLE
    down = build_news_context(_Repo([], fail=True), symbol="BTCUSDT", as_of_ms=5_000, config=NewsConfig())
    assert down.context_status is ContextStatus.ERROR
    assert down.storage_availability == "unavailable"
    invalid = build_news_context(_Repo([]), symbol="BTCUSDT", as_of_ms=-1, config=NewsConfig())
    assert invalid.context_status is ContextStatus.ERROR


def test_ordering_and_duplicate_suppression() -> None:
    repo = _Repo(
        [
            _row(event_id="nev_b", available_at_ms=4_000),
            _row(event_id="nev_a", available_at_ms=2_000),
            _row(event_id="nev_a", available_at_ms=3_000, summary="later duplicate"),
        ]
    )
    ctx = build_news_context(repo, symbol="BTCUSDT", as_of_ms=9_000, config=NewsConfig(max_events_per_context=10))
    assert [e.event_id for e in ctx.events] == ["nev_a", "nev_b"]
    assert ctx.events[0].summary == "Exchange issue"


def test_advisory_disabled_by_default_and_decision_parity() -> None:
    candles = make_series(bullish_trend_closes())
    now = series_now_ms(candles)
    common = dict(symbol="BTCUSDT", category="linear", interval="15", candles=candles, now_ms=now)
    off = _pipe().evaluate(**common)
    ctx = build_news_context(
        _Repo([_row(severity="CRITICAL", sentiment="NEGATIVE", available_at_ms=now - 1_000, classification_at_ms=now - 1_000, published_at_ms=now - 2_000, first_observed_at_ms=now - 1_000)]),
        symbol="BTCUSDT",
        as_of_ms=now,
        config=NewsConfig(),
    )
    on = _pipe().evaluate(**common, news_advisory_enabled=True, news_context=ctx)
    def _boom():
        raise RuntimeError("down")

    failed = _pipe().evaluate(**common, news_advisory_enabled=True, news_context_loader=_boom)
    assert off.action == on.action == failed.action
    assert off.risk.verdict == on.risk.verdict == failed.risk.verdict
    assert off.risk.position_notional == on.risk.position_notional
    assert off.signal_strength == on.signal_strength == failed.signal_strength
    assert on.news_changed_decision is False
    assert on.to_public_dict()["news_changed_decision"] is False
    assert on.to_public_dict()["news_influence_label"].startswith("News Advisory Only")
    assert on.to_public_dict()["news_advisory"]["llm_recommendation"] is None
    trend_off = next(c for c in off.contributions if c.agent_id == "trend")
    trend_on = next(c for c in on.contributions if c.agent_id == "trend")
    assert trend_off.bias == trend_on.bias
    assert trend_off.confidence == trend_on.confidence
    assert "news_observation" not in trend_off.indicators
    assert trend_on.indicators["news_observation"]["consumed"] is True
    assert on.risk.indicators["news_observation"]["news_changed_decision"] is False
    market_on = next(c for c in on.contributions if c.agent_id == "market_data")
    momentum_on = next(c for c in on.contributions if c.agent_id == "momentum")
    assert market_on.indicators["news_observation"]["consumed"] is True
    assert momentum_on.bias == next(c for c in off.contributions if c.agent_id == "momentum").bias
    assert failed.news_advisory["storage_availability"] == "unavailable"
    assert off.execution_allowed is False
    assert agent_allow_live_default() is False


def test_memory_event_roundtrip_matches_classifier_shape() -> None:
    repo = InMemoryNewsRepository()
    event = ClassifiedEvent(
        event_id="nev_mem",
        category=EventCategory.GENERAL,
        severity=Severity.LOW,
        sentiment=Sentiment.NEUTRAL,
        verification=VerificationStatus.SINGLE_SOURCE,
        headline="Routine maintenance note for bitcoin",
        summary="Routine maintenance note for bitcoin",
        assets=("BTCUSDT",),
        article_content_hashes=("abc",),
        published_at_ms=1_000,
        first_observed_at_ms=2_000,
        available_at_ms=2_000,
        classification_at_ms=2_000,
        reason_codes=("severity:LOW",),
        warnings=(),
    )
    repo.upsert_event(event, owner_user_id=None)
    ctx = build_news_context(repo, symbol="btcusdt", as_of_time=2_000, config=NewsConfig())
    assert ctx.events[0].event_id == "nev_mem"
    assert ctx.events[0].sentiment != "SELL"
