"""Transport boundary for LLM calls. Tests inject a fake. Production uses OpenAI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LlmProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ProviderCompletion:
    content: object
    prompt_tokens: int
    completion_tokens: int
    model: str


class LlmTransport(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout_s: float,
    ) -> ProviderCompletion: ...
