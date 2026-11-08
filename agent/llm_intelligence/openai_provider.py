"""OpenAI transport. Lazy SDK import. No calls when key or model is missing."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.llm_intelligence.provider_protocol import LlmProviderError, ProviderCompletion
from agent.llm_intelligence.schemas import SCHEMA_VERSION

_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "string"},
        "symbol": {"type": "string"},
        "suggested_action": {"type": "string", "enum": ["BUY", "SELL", "HOLD", "ABSTAIN"]},
        "technical_bias": {"type": "string"},
        "news_bias": {"type": "string"},
        "conflict_detected": {"type": "boolean"},
        "reason": {"type": "string"},
        "risk_warnings": {"type": "array", "items": {"type": "string"}},
        "evidence_event_ids": {"type": "array", "items": {"type": "string"}},
        "uncertainty": {"type": "string"},
        "abstain": {"type": "boolean"},
    },
    "required": [
        "schema_version",
        "symbol",
        "suggested_action",
        "technical_bias",
        "news_bias",
        "conflict_detected",
        "reason",
        "risk_warnings",
        "evidence_event_ids",
        "uncertainty",
        "abstain",
    ],
}


def _default_client_factory(*, api_key: str, timeout: float) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise LlmProviderError("sdk_unavailable", "openai package is not installed") from exc
    return OpenAI(api_key=api_key, timeout=timeout)


class OpenAiProvider:
    """Server-side client. The API key never leaves this process."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_s: float = 20.0,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._client_factory = client_factory or _default_client_factory

    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout_s: float,
    ) -> ProviderCompletion:
        if not self.api_key or not self.model:
            raise LlmProviderError("unconfigured", "Missing OpenAI key or model")
        if model != self.model:
            raise LlmProviderError("model_mismatch", "Refusing to substitute the configured model")
        client = self._client_factory(api_key=self.api_key, timeout=timeout_s or self.timeout_s)
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                timeout=timeout_s or self.timeout_s,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "cryptonova_llm_decision_support",
                        "strict": True,
                        "schema": _JSON_SCHEMA,
                    },
                },
            )
        except LlmProviderError:
            raise
        except Exception as exc:  # noqa: BLE001 — map SDK errors without leaking the key
            name = type(exc).__name__.lower()
            text = str(exc).lower()
            if "timeout" in name or "timeout" in text:
                raise LlmProviderError("timeout", "OpenAI request timed out") from exc
            if "ratelimit" in name or "rate limit" in text or "429" in text:
                raise LlmProviderError("rate_limit", "OpenAI rate limit") from exc
            raise LlmProviderError("provider_error", "OpenAI request failed") from exc
        returned = str(getattr(response, "model", "") or "")
        if returned and returned != self.model:
            raise LlmProviderError("model_mismatch", "Provider returned a different model")
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LlmProviderError("malformed", "OpenAI response had no choices")
        content = getattr(choices[0].message, "content", None)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        return ProviderCompletion(
            content=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=self.model,
        )


def response_schema_version() -> str:
    return SCHEMA_VERSION
