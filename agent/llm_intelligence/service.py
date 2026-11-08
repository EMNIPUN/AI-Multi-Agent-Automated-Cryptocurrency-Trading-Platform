"""Post-decision LLM advisory. Failures never change the deterministic signal."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from agent.llm_intelligence.audit_repository import LlmAuditRepository, LlmStorageError
from agent.llm_intelligence.budget import BudgetGuard
from agent.llm_intelligence.config import LlmConfig
from agent.llm_intelligence.context_builder import build_llm_input, messages_for
from agent.llm_intelligence.decision_support import agreement_status
from agent.llm_intelligence.observability import comparison_report
from agent.llm_intelligence.provider_protocol import LlmProviderError, LlmTransport
from agent.llm_intelligence.schemas import ADVISORY_LABEL, LlmEvaluation, PROMPT_TEMPLATE_VERSION
from agent.llm_intelligence.validation import validate_model_output


def view_from_decision(decision: Any) -> dict[str, Any]:
    return {
        "symbol": decision.symbol,
        "category": decision.category,
        "interval": decision.interval,
        "timestamp_ms": decision.timestamp_ms,
        "decision_id": decision.decision_id,
        "coordinator_action": decision.action.value,
        "risk_verdict": decision.risk.verdict.value,
        "position_notional": decision.risk.position_notional,
        "signal_strength": decision.signal_strength,
        "contributions": decision.to_public_dict()["contributions"],
    }


class LlmDecisionSupportService:
    def __init__(
        self,
        *,
        config: LlmConfig,
        repository: LlmAuditRepository,
        provider: LlmTransport | None = None,
        sleep: Callable[[float], None] | None = None,
        budget: BudgetGuard | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.provider = provider
        self._sleep = sleep or (lambda _seconds: None)
        self.budget = budget or BudgetGuard(config)
        self._provider_calls = 0

    @property
    def provider_calls(self) -> int:
        return self._provider_calls

    def status(self, now_ms: int = 0) -> dict[str, Any]:
        body = self.config.public_status()
        body.update(
            {
                "label": ADVISORY_LABEL,
                "storage_kind": self.repository.storage_kind(),
                "storage_available": self.repository.ready(),
                "schema_version": "69D.1.0",
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "budget": self.budget.snapshot(now_ms),
                "provider_calls_this_process": self._provider_calls,
                "automatic_calls": False,
            }
        )
        return body

    def list_evaluations(self, *, limit: int = 50) -> list[dict[str, Any]]:
        if not self.repository.ready():
            return []
        return [row.to_public_dict() for row in self.repository.list_recent(limit=limit)]

    def get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        if not self.repository.ready():
            return None
        row = self.repository.get(evaluation_id)
        return None if row is None else row.to_public_dict()

    def report(self) -> dict[str, Any]:
        rows = [] if not self.repository.ready() else self.repository.list_recent(limit=100)
        body = comparison_report(rows)
        body["llm_changed_decision"] = False
        body["profitability_claimed"] = False
        return body

    def evaluate(
        self,
        view: dict[str, Any],
        *,
        news_context: Any = None,
        exposure: dict | None = None,
        idempotency_key: str | None = None,
        now_ms: int,
    ) -> LlmEvaluation:
        symbol = str(view.get("symbol") or "").upper()
        action = str(view.get("coordinator_action") or view.get("action") or "")
        verdict = str(view.get("risk_verdict") or "")
        notional = view.get("position_notional")
        decision_id = str(view.get("decision_id") or view.get("signal_decision_id") or "")
        interval = str(view.get("interval") or "")
        if not self.config.enabled:
            return self._finish(
                self._shell(
                    status="disabled",
                    symbol=symbol,
                    interval=interval,
                    decision_id=decision_id,
                    action=action,
                    verdict=verdict,
                    notional=notional,
                    now_ms=now_ms,
                    key=idempotency_key or "disabled",
                    error_code="disabled",
                    reason="NEWS_LLM_ENABLED is false",
                ),
                persist=False,
            )
        if not self.config.api_key:
            return self._shell(
                status="missing_api_key",
                symbol=symbol,
                interval=interval,
                decision_id=decision_id,
                action=action,
                verdict=verdict,
                notional=notional,
                now_ms=now_ms,
                key=idempotency_key or "missing-key",
                error_code="missing_api_key",
                reason="OPENAI_API_KEY is empty",
            )
        if not self.config.model:
            return self._shell(
                status="missing_model",
                symbol=symbol,
                interval=interval,
                decision_id=decision_id,
                action=action,
                verdict=verdict,
                notional=notional,
                now_ms=now_ms,
                key=idempotency_key or "missing-model",
                error_code="missing_model",
                reason="CRYPTONOVA_LLM_MODEL is empty",
            )
        payload = build_llm_input(view, news_context, exposure)
        key = (idempotency_key or f"{decision_id}:{payload['context_hash']}:{self.config.model}")[:128]
        existing = self.repository.get_by_idempotency(key)
        if existing is not None:
            from dataclasses import replace

            return replace(existing, idempotent_replay=True)
        if not self.repository.ready():
            return self._shell(
                status="storage_unavailable",
                symbol=symbol,
                interval=interval,
                decision_id=decision_id,
                action=action,
                verdict=verdict,
                notional=notional,
                now_ms=now_ms,
                key=key,
                error_code="storage_unavailable",
                reason="LLM audit storage is unavailable",
                warnings=tuple(payload["news"]["warnings"]),
                context_hash=payload["context_hash"],
            )
        gate = self.budget.try_begin(now_ms)
        if gate:
            return self._shell(
                status=gate,
                symbol=symbol,
                interval=interval,
                decision_id=decision_id,
                action=action,
                verdict=verdict,
                notional=notional,
                now_ms=now_ms,
                key=key,
                error_code=gate,
                reason=gate,
                warnings=tuple(payload["news"]["warnings"]),
                context_hash=payload["context_hash"],
            )
        try:
            completion, error = self._call(payload)
            if error is not None:
                record = self._shell(
                    status=error.code if error.code in {"timeout", "rate_limit"} else "provider_error",
                    symbol=symbol,
                    interval=interval,
                    decision_id=decision_id,
                    action=action,
                    verdict=verdict,
                    notional=notional,
                    now_ms=now_ms,
                    key=key,
                    error_code=error.code,
                    reason=error.message,
                    warnings=tuple(payload["news"]["warnings"]),
                    context_hash=payload["context_hash"],
                    provider_called=True,
                )
                if error.code == "timeout":
                    record = _with_status(record, "provider_timeout")
                elif error.code == "rate_limit":
                    record = _with_status(record, "provider_rate_limited")
                return self._finish(record)
            outcome = validate_model_output(
                completion.content,
                symbol=symbol,
                allowed_event_ids=set(payload["allowed_event_ids"]),
            )
            cost = self._cost(completion.prompt_tokens, completion.completion_tokens)
            self.budget.add_cost(now_ms, cost)
            usage = {
                "prompt_tokens": completion.prompt_tokens,
                "completion_tokens": completion.completion_tokens,
            }
            if not outcome.ok or outcome.output is None:
                return self._finish(
                    self._shell(
                        status="rejected",
                        symbol=symbol,
                        interval=interval,
                        decision_id=decision_id,
                        action=action,
                        verdict=verdict,
                        notional=notional,
                        now_ms=now_ms,
                        key=key,
                        error_code=outcome.code,
                        reason="Model output rejected",
                        warnings=tuple(payload["news"]["warnings"]),
                        context_hash=payload["context_hash"],
                        provider_called=True,
                        validation=outcome.code,
                        usage=usage,
                        cost=cost,
                    )
                )
            output = outcome.output
            agree = agreement_status(
                coordinator_action=action,
                suggested_action=output["suggested_action"],
                abstain=output["abstain"],
                valid=True,
            )
            return self._finish(
                self._shell(
                    status="accepted",
                    symbol=symbol,
                    interval=interval,
                    decision_id=decision_id,
                    action=action,
                    verdict=verdict,
                    notional=notional,
                    now_ms=now_ms,
                    key=key,
                    suggested=output["suggested_action"],
                    agreement=agree,
                    conflict=bool(output["conflict_detected"]),
                    reason=output["reason"],
                    risk_warnings=tuple(output["risk_warnings"]),
                    evidence=tuple(output["evidence_event_ids"]),
                    uncertainty=output["uncertainty"],
                    abstain=bool(output["abstain"]),
                    technical_bias=output["technical_bias"],
                    news_bias=output["news_bias"],
                    warnings=tuple(payload["news"]["warnings"]),
                    context_hash=payload["context_hash"],
                    provider_called=True,
                    validation="accepted",
                    usage=usage,
                    cost=cost,
                )
            )
        finally:
            self.budget.end()

    def _call(self, payload: dict[str, Any]):
        if self.provider is None:
            return None, LlmProviderError("provider_missing", "No LLM transport configured")
        messages = messages_for(payload)
        system = messages[0]["content"]
        if payload["news"]["events"] and any(
            event["untrusted_summary"] and event["untrusted_summary"] in system
            for event in payload["news"]["events"]
        ):
            return None, LlmProviderError("prompt_boundary", "News text leaked into system instructions")
        last: LlmProviderError | None = None
        for attempt in range(self.config.max_rate_limit_retries + 1):
            try:
                self._provider_calls += 1
                return self.provider.complete(
                    messages=messages,
                    model=self.config.model,
                    timeout_s=self.config.timeout_seconds,
                ), None
            except LlmProviderError as exc:
                last = exc
                if exc.code == "rate_limit" and attempt < self.config.max_rate_limit_retries:
                    self._sleep(0.01 * (attempt + 1))
                    continue
                return None, exc
        return None, last or LlmProviderError("provider_error", "LLM call failed")

    def _cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        usd = (
            prompt_tokens / 1_000_000 * self.config.input_usd_per_million
            + completion_tokens / 1_000_000 * self.config.output_usd_per_million
        )
        return max(self.config.min_call_usd, round(usd, 6))

    def _finish(self, record: LlmEvaluation, *, persist: bool = True) -> LlmEvaluation:
        if not persist or not self.repository.ready():
            return record
        try:
            from dataclasses import replace

            to_store = replace(record, persisted=True, storage_error=None)
            return self.repository.save(to_store)
        except LlmStorageError as exc:
            from dataclasses import replace

            return replace(record, persisted=False, storage_error=exc.code)

    def _shell(
        self,
        *,
        status: str,
        symbol: str,
        interval: str,
        decision_id: str,
        action: str,
        verdict: str,
        notional: float | None,
        now_ms: int,
        key: str,
        reason: str,
        error_code: str | None = None,
        suggested: str | None = None,
        agreement: str = "not_applicable",
        conflict: bool = False,
        risk_warnings: tuple[str, ...] = (),
        evidence: tuple[str, ...] = (),
        uncertainty: str = "UNKNOWN",
        abstain: bool = False,
        technical_bias: str = "UNKNOWN",
        news_bias: str = "UNKNOWN",
        warnings: tuple[str, ...] = (),
        context_hash: str = "",
        provider_called: bool = False,
        validation: str = "not_run",
        usage: dict[str, int] | None = None,
        cost: float = 0.0,
    ) -> LlmEvaluation:
        return LlmEvaluation(
            evaluation_id="lle_" + uuid.uuid4().hex[:16],
            status=status,
            symbol=symbol,
            interval=interval,
            signal_decision_id=decision_id,
            coordinator_action=action,
            risk_verdict=verdict,
            position_notional=notional if isinstance(notional, (int, float)) else None,
            suggested_action=suggested,
            agreement=agreement,
            conflict_detected=conflict,
            reason=reason[:500],
            risk_warnings=risk_warnings,
            evidence_event_ids=evidence,
            uncertainty=uncertainty,
            abstain=abstain,
            model=self.config.model,
            provider="openai" if self.config.model else "none",
            prompt_template_version=PROMPT_TEMPLATE_VERSION,
            context_hash=context_hash,
            validation_result=validation,
            token_usage=usage or {"prompt_tokens": 0, "completion_tokens": 0},
            estimated_cost_usd=cost,
            persisted=False,
            storage_error=None if self.repository.ready() else "storage_unavailable",
            provider_called=provider_called,
            idempotency_key=key,
            idempotent_replay=False,
            warnings=warnings,
            requested_at_ms=now_ms,
            completed_at_ms=now_ms,
            technical_bias=technical_bias,
            news_bias=news_bias,
            error_code=error_code,
            llm_changed_decision=False,
            execution_allowed=False,
            places_orders=False,
        )


def _with_status(record: LlmEvaluation, status: str) -> LlmEvaluation:
    from dataclasses import replace

    return replace(record, status=status)
