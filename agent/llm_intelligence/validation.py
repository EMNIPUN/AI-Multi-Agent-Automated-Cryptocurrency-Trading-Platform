"""Server-side rejection of model output. Never grants execution authority."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from agent.llm_intelligence.schemas import (
    ALLOWED_ACTIONS,
    FORBIDDEN_OUTPUT_KEYS,
    NEWS_BIAS,
    SCHEMA_VERSION,
    TECHNICAL_BIAS,
    UNCERTAINTY,
)

_MAX_REASON = 500
_MAX_WARNING = 160
_MAX_WARNINGS = 8
_ORDER_LANGUAGE = re.compile(
    r"\b(place\s+order|place\s+a\s+trade|execution_allowed|bypass\s+risk|"
    r"market\s+buy|market\s+sell|send\s+order)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    code: str
    output: dict | None
    reason: str


def _as_object(raw: object) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def validate_model_output(
    raw: object,
    *,
    symbol: str,
    allowed_event_ids: set[str],
) -> ValidationOutcome:
    body = _as_object(raw)
    if body is None:
        return ValidationOutcome(False, "malformed_json", None, "Model output was not a JSON object")
    leaked = FORBIDDEN_OUTPUT_KEYS.intersection(body)
    if leaked:
        return ValidationOutcome(
            False,
            "order_authorization",
            None,
            "Model output attempted to set execution fields",
        )
    action = str(body.get("suggested_action") or "").upper()
    if action not in ALLOWED_ACTIONS:
        return ValidationOutcome(False, "unsupported_action", None, "Unsupported suggested action")
    if str(body.get("symbol") or "").upper() != symbol.upper():
        return ValidationOutcome(False, "symbol_mismatch", None, "Symbol does not match the request")
    if str(body.get("schema_version") or "") != SCHEMA_VERSION:
        return ValidationOutcome(False, "schema_mismatch", None, "Unexpected schema version")
    reason = str(body.get("reason") or "").strip()
    if len(reason) > _MAX_REASON or _ORDER_LANGUAGE.search(reason):
        return ValidationOutcome(False, "invalid_reason", None, "Reason rejected")
    warnings_raw = body.get("risk_warnings") or []
    if not isinstance(warnings_raw, list) or len(warnings_raw) > _MAX_WARNINGS:
        return ValidationOutcome(False, "invalid_warnings", None, "Warnings rejected")
    warnings: list[str] = []
    for item in warnings_raw:
        text = str(item).strip()
        if not text or len(text) > _MAX_WARNING or _ORDER_LANGUAGE.search(text):
            return ValidationOutcome(False, "invalid_warnings", None, "Warnings rejected")
        warnings.append(text)
    evidence = body.get("evidence_event_ids") or []
    if not isinstance(evidence, list):
        return ValidationOutcome(False, "fabricated_evidence", None, "Evidence was not a list")
    evidence_ids = [str(item) for item in evidence]
    if any(item not in allowed_event_ids for item in evidence_ids):
        return ValidationOutcome(False, "fabricated_evidence", None, "Unknown event id")
    technical = str(body.get("technical_bias") or "UNKNOWN").upper()
    news_bias = str(body.get("news_bias") or "UNKNOWN").upper()
    uncertainty = str(body.get("uncertainty") or "UNKNOWN").upper()
    if technical not in TECHNICAL_BIAS or news_bias not in NEWS_BIAS or uncertainty not in UNCERTAINTY:
        return ValidationOutcome(False, "invalid_bias", None, "Bias or uncertainty rejected")
    abstain = bool(body.get("abstain"))
    if abstain and action != "ABSTAIN":
        return ValidationOutcome(False, "inconsistent_abstain", None, "Abstain flag disagrees with action")
    if action == "ABSTAIN":
        abstain = True
    conflict = body.get("conflict_detected")
    if not isinstance(conflict, bool):
        return ValidationOutcome(False, "invalid_conflict", None, "conflict_detected must be boolean")
    return ValidationOutcome(
        True,
        "accepted",
        {
            "schema_version": SCHEMA_VERSION,
            "symbol": symbol.upper(),
            "suggested_action": action,
            "technical_bias": technical,
            "news_bias": news_bias,
            "conflict_detected": conflict,
            "reason": reason,
            "risk_warnings": warnings,
            "evidence_event_ids": evidence_ids,
            "uncertainty": uncertainty,
            "abstain": abstain,
        },
        reason,
    )
