"""Structured agent / tool result contracts for Orchestrator V2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ResultStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass
class ToolResultEnvelope:
    tool: str
    status: ResultStatus
    verified: dict[str, Any] = field(default_factory=dict)
    model_commentary: str | None = None
    error_code: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    call_id: str | None = None
    duration_ms: int | None = None

    def to_public(self) -> dict[str, Any]:
        body = asdict(self)
        body["status"] = self.status.value
        return body


def wrap_tool_result(
    tool: str,
    raw: dict[str, Any] | Any,
    *,
    call_id: str | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
) -> ToolResultEnvelope:
    if error:
        return ToolResultEnvelope(
            tool=tool,
            status=ResultStatus.ERROR,
            verified={},
            error_code=error,
            call_id=call_id,
            duration_ms=duration_ms,
        )
    if not isinstance(raw, dict):
        return ToolResultEnvelope(
            tool=tool,
            status=ResultStatus.PARTIAL,
            verified={"value": raw},
            call_id=call_id,
            duration_ms=duration_ms,
        )
    status = ResultStatus.SUCCESS
    if raw.get("ok") is False:
        status = ResultStatus.BLOCKED if "BLOCKED" in str(raw.get("summary") or "").upper() else ResultStatus.ERROR
    action = str(raw.get("analysis_action") or raw.get("action") or "").upper()
    if action in {"BLOCKED", "HOLD"} and tool in {"run_full_analysis", "analyze_symbol"}:
        status = ResultStatus.SUCCESS  # verified HOLD/BLOCKED is still a successful analysis
    if raw.get("reason") == "market_data_unavailable":
        status = ResultStatus.UNAVAILABLE
    if raw.get("stale") is True:
        status = ResultStatus.STALE
    # Strip speculative narrative fields from verified facts when present.
    verified = {
        k: v
        for k, v in raw.items()
        if k
        not in {
            "model_commentary",
            "llm_changed_decision",
        }
    }
    return ToolResultEnvelope(
        tool=tool,
        status=status,
        verified=verified,
        model_commentary=str(raw.get("model_commentary") or "") or None,
        call_id=call_id,
        duration_ms=duration_ms,
        reason_codes=[str(raw.get("risk_verdict") or "")] if raw.get("risk_verdict") else [],
    )
