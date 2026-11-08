"""LLM feature flags and spend limits. Defaults keep the provider off."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool = False
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 20.0
    max_calls_per_hour: int = 20
    daily_budget_usd: float = 1.0
    max_concurrency: int = 2
    max_rate_limit_retries: int = 2
    min_call_usd: float = 0.01
    input_usd_per_million: float = 5.0
    output_usd_per_million: float = 15.0

    @classmethod
    def from_env(cls) -> LlmConfig:
        return cls(
            enabled=_env_bool("NEWS_LLM_ENABLED", False),
            api_key=(os.getenv("OPENAI_API_KEY") or "").strip(),
            model=(os.getenv("CRYPTONOVA_LLM_MODEL") or "").strip(),
            timeout_seconds=max(1.0, _env_float("CRYPTONOVA_LLM_TIMEOUT_SECONDS", 20.0)),
            max_calls_per_hour=max(1, _env_int("CRYPTONOVA_LLM_MAX_CALLS_PER_HOUR", 20)),
            daily_budget_usd=max(0.0, _env_float("CRYPTONOVA_LLM_DAILY_BUDGET_USD", 1.0)),
        )

    def public_status(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "model_configured": bool(self.model),
            "api_key_configured": bool(self.api_key),
            "model": self.model if self.model else None,
            "provider": "openai" if self.model else None,
            "timeout_seconds": self.timeout_seconds,
            "max_calls_per_hour": self.max_calls_per_hour,
            "daily_budget_usd": self.daily_budget_usd,
            "max_concurrency": self.max_concurrency,
            "places_orders": False,
            "llm_changed_decision": False,
        }
