"""LLM service singleton. In-memory audit storage is test-only."""

from __future__ import annotations

import threading

from agent.llm_intelligence.audit_repository import UnavailableLlmAuditRepository
from agent.llm_intelligence.config import LlmConfig
from agent.llm_intelligence.openai_provider import OpenAiProvider
from agent.llm_intelligence.service import LlmDecisionSupportService

_LOCK = threading.Lock()
_SERVICE: LlmDecisionSupportService | None = None


def _config_from_settings(settings) -> LlmConfig:
    return LlmConfig(
        enabled=bool(settings.news_llm_enabled),
        api_key=(settings.openai_api_key or "").strip(),
        model=(settings.cryptonova_llm_model or "").strip(),
        timeout_seconds=max(1.0, float(settings.cryptonova_llm_timeout_seconds or 20)),
        max_calls_per_hour=max(1, int(settings.cryptonova_llm_max_calls_per_hour or 20)),
        daily_budget_usd=max(0.0, float(settings.cryptonova_llm_daily_budget_usd or 1)),
    )


def _build_runtime_service(config: LlmConfig) -> LlmDecisionSupportService:
    reason = (
        "storage_unavailable: app.llm_evaluations missing or DATABASE_URL unreachable. "
        "Apply Alembic 20261108_0008 and 20261108_0009 on the development target first."
    )
    try:
        from apps.api.app.db import create_db_engine
        from apps.api.app.llm.pg_repository import PostgresLlmAuditRepository

        engine = create_db_engine()
        repo = PostgresLlmAuditRepository(engine)
        from agent.llm_intelligence.durable_budget import FailClosedBudget
        from apps.api.app.llm.durable_budget_pg import PostgresDurableBudget

        budget = PostgresDurableBudget(
            engine,
            max_calls_per_hour=config.max_calls_per_hour,
            daily_budget_usd=config.daily_budget_usd,
            min_call_usd=config.min_call_usd,
        )
        if not budget.ready():
            budget = FailClosedBudget("migration 20261108_0011 is not applied")
        if not repo.ready():
            return LlmDecisionSupportService(
                config=config,
                repository=UnavailableLlmAuditRepository(reason),
                provider=OpenAiProvider(
                    api_key=config.api_key,
                    model=config.model,
                    timeout_s=config.timeout_seconds,
                ),
                budget=budget,
            )
        return LlmDecisionSupportService(
            config=config,
            repository=repo,
            provider=OpenAiProvider(
                api_key=config.api_key,
                model=config.model,
                timeout_s=config.timeout_seconds,
            ),
            budget=budget,
        )
    except Exception:
        from agent.llm_intelligence.durable_budget import FailClosedBudget

        return LlmDecisionSupportService(
            config=config,
            repository=UnavailableLlmAuditRepository(reason),
            provider=None,
            budget=FailClosedBudget("llm storage unavailable"),
        )


def get_llm_service(config: LlmConfig | None = None) -> LlmDecisionSupportService:
    global _SERVICE
    with _LOCK:
        if _SERVICE is None:
            _SERVICE = _build_runtime_service(config or LlmConfig.from_env())
        elif config is not None:
            _SERVICE.config = config
        return _SERVICE


def reset_llm_service_for_tests(service: LlmDecisionSupportService | None) -> None:
    global _SERVICE
    with _LOCK:
        _SERVICE = service
