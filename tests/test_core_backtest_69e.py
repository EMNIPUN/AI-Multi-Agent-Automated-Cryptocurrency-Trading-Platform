"""Prompt 69E — point-in-time shadow replay. Decisions stay on the 68A path."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

os.environ.setdefault("SUPABASE_SOT_ENABLED", "false")

from agent.backtest.config import BacktestConfig
from agent.backtest.data import synthetic_trend_candles
from agent.backtest.news_revisions import (
    NewsRevision,
    build_historical_news_context,
    refuse_latest_row_as_history,
)
from agent.backtest.runner import run_backtest
from agent.backtest.shadow import RecordedLlmAdvice, annotate_shadow, research_policy_status
from apps.api.app.backtests.revision_archive import PostgresRevisionArchive, RevisionStorageError
from apps.api.app.config import ApiSettings, agent_allow_live_default, clear_settings_cache
from apps.api.app.factory import create_app


def _rev(**overrides) -> NewsRevision:
    base = dict(
        event_id="nev_a",
        revision_id="rev_1",
        revision_number=1,
        classification_version="69C.1.0",
        severity="HIGH",
        sentiment="NEGATIVE",
        verification="SINGLE_SOURCE",
        symbols=("BTCUSDT",),
        source_evidence=("src_1",),
        published_at_ms=1_000,
        first_observed_at_ms=2_000,
        first_available_at_ms=3_000,
        revision_available_at_ms=3_000,
        content_hash="hash_1",
        recorded_at_ms=3_000,
        delayed_provider=False,
    )
    base.update(overrides)
    return NewsRevision(**base)


def test_revision_selection_excludes_future_backfill_and_other_symbols() -> None:
    early = build_historical_news_context(
        "BTCUSDT",
        3_000,
        [
            _rev(),
            _rev(revision_id="rev_2", revision_number=2, revision_available_at_ms=9_000, recorded_at_ms=9_000, severity="CRITICAL"),
            _rev(event_id="nev_future", revision_id="rev_f", first_available_at_ms=8_000, revision_available_at_ms=8_000, recorded_at_ms=8_000),
            _rev(event_id="nev_eth", revision_id="rev_e", symbols=("ETHUSDT",)),
            _rev(
                event_id="nev_backfill",
                revision_id="rev_b",
                published_at_ms=500,
                first_available_at_ms=600,
                revision_available_at_ms=700,
                recorded_at_ms=20_000,
            ),
        ],
        archive_complete=True,
    )
    assert [event["revision_id"] for event in early.events] == ["rev_1"]
    assert early.events[0]["severity"] == "HIGH"
    assert early.future_excluded == 3
    assert early.backfill_excluded == 3
    assert "nev_backfill" not in {event["event_id"] for event in early.events}
    assert "backfilled_news_not_yet_available" in early.warnings
    later = build_historical_news_context(
        "BTCUSDT",
        9_000,
        [_rev(), _rev(revision_id="rev_2", revision_number=2, revision_available_at_ms=9_000, recorded_at_ms=9_000, severity="CRITICAL", content_hash="hash_2")],
        archive_complete=True,
    )
    assert later.events[0]["revision_id"] == "rev_2"
    assert later.events[0]["severity"] == "CRITICAL"


def test_missing_timestamps_delay_and_latest_row_are_not_history() -> None:
    missing_available = build_historical_news_context(
        "BTCUSDT",
        5_000,
        [_rev(first_available_at_ms=None)],
        archive_complete=True,
    )
    assert missing_available.events == ()
    assert missing_available.historical_news_backtest_valid is False
    assert "incomplete_revision_history" in missing_available.warnings

    missing_published = build_historical_news_context(
        "BTCUSDT",
        5_000,
        [_rev(published_at_ms=None)],
        archive_complete=True,
    )
    assert missing_published.events[0]["event_id"] == "nev_a"
    assert "missing_publication_time" in missing_published.warnings

    delayed = build_historical_news_context(
        "BTCUSDT",
        5_000,
        [_rev(delayed_provider=True)],
        archive_complete=True,
    )
    assert "delayed_provider_feed" in delayed.warnings

    refused = refuse_latest_row_as_history("BTCUSDT", 5_000)
    assert refused.events == ()
    assert refused.historical_news_backtest_valid is False
    assert "latest_upsert_is_not_historical_provenance" in refused.warnings

    invalid = build_historical_news_context("BTCUSDT", -1, [_rev()])
    assert invalid.warnings[0] == "invalid_timestamp"


def test_shadow_modes_do_not_change_the_technical_result(tmp_path: Path) -> None:
    candles = synthetic_trend_candles(n=40)
    result = run_backtest(
        BacktestConfig(min_confirmed_bars=30),
        candles=candles,
        journal_dir=tmp_path,
    )
    assert result.status.value == "completed"
    before = (
        [(row.action, row.risk_verdict, row.position_notional) for row in result.decisions],
        result.final_available_balance,
        result.final_marked_equity,
        result.dataset.content_hash,
    )
    journal = Path(result.journal_path or "")
    size_before = journal.stat().st_size
    revisions = (
        _rev(
            published_at_ms=result.decisions[0].now_ms - 5_000,
            first_observed_at_ms=result.decisions[0].now_ms - 4_000,
            first_available_at_ms=result.decisions[0].now_ms - 3_000,
            revision_available_at_ms=result.decisions[0].now_ms - 3_000,
            recorded_at_ms=result.decisions[0].now_ms - 3_000,
        ),
    )
    advice = (
        RecordedLlmAdvice(
            evaluation_id="lle_hist",
            symbol="BTCUSDT",
            completed_at_ms=result.decisions[0].now_ms - 1,
            suggested_action="SELL",
            abstain=False,
            validation_result="accepted",
            evidence_event_ids=("nev_a",),
            model="gpt-test",
            prompt_version="69D.prompt.1",
        ),
        RecordedLlmAdvice(
            evaluation_id="lle_retro",
            symbol="BTCUSDT",
            completed_at_ms=result.decisions[0].now_ms - 1,
            suggested_action="BUY",
            abstain=False,
            validation_result="accepted",
            evidence_event_ids=(),
            model="gpt-test",
            prompt_version="69D.prompt.1",
            retrospective=True,
        ),
    )
    news = annotate_shadow(result, mode="news_advisory_shadow", revisions=revisions, archive_complete=False)
    llm = annotate_shadow(result, mode="llm_advisory_shadow", revisions=revisions, llm_records=advice)
    after = (
        [(row.action, row.risk_verdict, row.position_notional) for row in news.decisions],
        news.final_available_balance,
        news.final_marked_equity,
        news.dataset.content_hash,
    )
    assert before == after
    assert [(row.action, row.risk_verdict, row.position_notional) for row in llm.decisions] == before[0]
    assert news.extras["shadow_69e"]["decisions_unchanged"] is True
    assert news.extras["shadow_69e"]["news_changed_decision"] is False
    assert news.extras["shadow_69e"]["historical_news_backtest_valid"] is False
    assert news.extras["shadow_69e"]["performance_improvement_claimed"] is False
    assert news.extras["shadow_69e"]["profitability_claimed"] is False
    assert llm.extras["shadow_69e"]["llm_changed_decision"] is False
    assert llm.extras["shadow_69e"]["openai_called"] is False
    assert llm.extras["shadow_69e"]["metrics"]["technical"]["net_realized_pnl"] == result.analytics["net_realized_pnl"]
    assert llm.extras["shadow_69e"]["lookahead_violations"] == 0
    assert "Advisory Only" in llm.extras["shadow_69e"]["advisory_label"]
    again = annotate_shadow(result, mode="news_advisory_shadow", revisions=revisions)
    assert again.result_hash == news.result_hash
    assert again.dataset.content_hash == result.dataset.content_hash
    assert journal.stat().st_size == size_before
    assert research_policy_status()["activated"] is False
    assert agent_allow_live_default() is False
    for path in Path("agent/backtest").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "from openai" not in text
        assert "import openai" not in text
        assert "place_order(" not in text


def test_storage_unavailable_and_shadow_status_does_not_call_a_model() -> None:
    with pytest.raises(RevisionStorageError):
        PostgresRevisionArchive(create_engine("sqlite://"))

    class _Conn:
        def __enter__(self):
            raise SQLAlchemyError("down")

        def __exit__(self, *_args):
            return False

    class _Down:
        class dialect:
            name = "postgresql"

        def connect(self):
            return _Conn()

    archive = PostgresRevisionArchive(_Down())  # type: ignore[arg-type]
    assert archive.ready() is False
    with pytest.raises(RevisionStorageError):
        archive.save_shadow({"run_id": "bt_test"})

    text = Path("apps/api/alembic/versions/20261108_0010_news_revisions_69e.py").read_text(encoding="utf-8")
    assert 'down_revision: Union[str, None] = "20261108_0009"' in text
    assert "news_event_revisions are append-only" in text
    assert "news_event_revisions_select_own" in text

    clear_settings_cache()
    settings = ApiSettings(
        _env_file=None,
        api_host="127.0.0.1",
        backtest_read_api_enabled=True,
        news_llm_enabled=False,
        news_auto_collection_enabled=False,
    )
    client = TestClient(create_app(settings))
    allowed = client.get("/api/v1/backtests/shadow-status")
    assert allowed.status_code == 200
    body = allowed.json()
    assert body["historical_news_backtest_valid"] is False
    assert body["openai_called"] is False
    assert body["provenance_status"] == "incomplete"
    if body["last_verified_development_revision"] in {"20261108_0011", "20261108_0012"}:
        assert body["revision_probe"] == "ok"
        assert body["migrations_pending"] == []
        assert body["llm_budget_durable_across_processes"] is True
    else:
        assert body["revision_probe"] == "unavailable"
        assert "20261108_0010" in body["migrations_pending"]
        assert body["llm_budget_durable_across_processes"] is False
    denied = client.get("/api/v1/backtests/shadow-status", headers={"x-forwarded-for": "203.0.113.8"})
    assert denied.status_code == 403
    clear_settings_cache()
