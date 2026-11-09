"""Prompt 70A — revision planning and durable budget behavior. No paid calls."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from agent.llm_intelligence.audit_repository import InMemoryLlmAuditRepository, LlmStorageError
from agent.llm_intelligence.config import LlmConfig
from agent.llm_intelligence.durable_budget import FailClosedBudget, InMemoryDurableBudget, SharedLedger
from agent.llm_intelligence.provider_protocol import ProviderCompletion
from agent.llm_intelligence.service import LlmDecisionSupportService
from agent.news.revisions import plan_revision
from agent.news.schemas import (
    ClassifiedEvent,
    EventCategory,
    Sentiment,
    Severity,
    VerificationStatus,
)
from apps.api.app.llm.durable_budget_pg import PostgresDurableBudget


def _event(**overrides) -> ClassifiedEvent:
    base = dict(
        event_id="nev_a",
        category=EventCategory.SECURITY_INCIDENT,
        severity=Severity.HIGH,
        sentiment=Sentiment.NEGATIVE,
        verification=VerificationStatus.SINGLE_SOURCE,
        headline="Exchange issue",
        summary="Exchange issue",
        assets=("BTCUSDT",),
        article_content_hashes=("hash_1",),
        published_at_ms=1_000,
        first_observed_at_ms=2_000,
        available_at_ms=3_000,
        classification_at_ms=4_000,
        reason_codes=("severity:HIGH",),
        warnings=(),
    )
    base.update(overrides)
    return ClassifiedEvent(**base)


def test_revision_plan_is_append_only_and_not_backdated() -> None:
    first = plan_revision(_event(), prior_number=0, prior_material=None, recorded_at_ms=4_000)
    assert first is not None
    assert first.revision_number == 1
    assert first.recorded_at_ms == 4_000
    assert first.revision_available_at_ms == 4_000
    assert first.published_at_ms == 1_000
    again = plan_revision(
        _event(),
        prior_number=1,
        prior_material="HIGH|NEGATIVE|SINGLE_SOURCE|rule_based_v1|hash_1",
        recorded_at_ms=5_000,
    )
    assert again is None
    changed = plan_revision(
        _event(severity=Severity.CRITICAL),
        prior_number=1,
        prior_material="HIGH|NEGATIVE|SINGLE_SOURCE|rule_based_v1|hash_1",
        recorded_at_ms=6_000,
    )
    assert changed is not None
    assert changed.revision_number == 2
    assert changed.recorded_at_ms == 6_000
    assert changed.revision_available_at_ms == 6_000


def test_durable_budget_survives_restart_and_releases_failures() -> None:
    ledger = SharedLedger()
    first = InMemoryDurableBudget(ledger, max_calls_per_hour=2, daily_budget_usd=0.02, min_call_usd=0.01)
    assert first.try_begin(1_000, idempotency_key="a") is None
    restarted = InMemoryDurableBudget(ledger, max_calls_per_hour=2, daily_budget_usd=0.02, min_call_usd=0.01)
    assert restarted.try_begin(1_100, idempotency_key="a") == "reservation_pending"
    assert restarted.try_begin(1_200, idempotency_key="b") is None
    assert restarted.try_begin(1_300, idempotency_key="c") == "hourly_cap"
    restarted.release("b")
    spend = InMemoryDurableBudget(ledger, max_calls_per_hour=5, daily_budget_usd=0.01, min_call_usd=0.01)
    assert spend.try_begin(2_000, idempotency_key="d") == "budget_exhausted"
    closed = FailClosedBudget("missing")
    assert closed.ready() is False
    assert closed.try_begin(1, idempotency_key="z") == "budget_storage_unavailable"


def test_fail_closed_budget_blocks_the_provider() -> None:
    class _Provider:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, **_kwargs):
            self.calls += 1
            return ProviderCompletion(content={}, prompt_tokens=1, completion_tokens=1, model="gpt-test")

    provider = _Provider()
    service = LlmDecisionSupportService(
        config=LlmConfig(enabled=True, api_key="test", model="gpt-test"),
        repository=InMemoryLlmAuditRepository(),
        provider=provider,
        budget=FailClosedBudget("down"),
    )
    row = service.evaluate(
        {
            "symbol": "BTCUSDT",
            "interval": "15",
            "decision_id": "dec",
            "coordinator_action": "HOLD",
            "risk_verdict": "VETO",
            "timestamp_ms": 10,
        },
        now_ms=10,
        idempotency_key="budget-1",
    )
    assert row.status == "budget_storage_unavailable"
    assert provider.calls == 0


def test_postgres_budget_rejects_sqlite() -> None:
    with pytest_raises():
        PostgresDurableBudget(create_engine("sqlite://"))


def pytest_raises():
    import pytest

    return pytest.raises(LlmStorageError)


class _Down:
    class dialect:
        name = "postgresql"

    def connect(self):
        return self

    def __enter__(self):
        raise SQLAlchemyError("down")

    def __exit__(self, *_args):
        return False


def test_postgres_budget_not_ready_fails_closed() -> None:
    budget = PostgresDurableBudget(_Down())  # type: ignore[arg-type]
    assert budget.ready() is False
    assert budget.try_begin(1, idempotency_key="k") == "budget_storage_unavailable"
