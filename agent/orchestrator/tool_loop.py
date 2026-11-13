"""Bounded OpenAI Responses tool loop with call_id continuity.

Never places orders itself — only invokes allowlisted tool callables after validation.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.orchestrator.budget import (
    BudgetReservation,
    commit_spend,
    release_spend,
    reserve_spend,
)
from agent.orchestrator.guard import redact, validate_tool_call
from agent.orchestrator.result_contracts import wrap_tool_result
from agent.orchestrator.tool_registry import is_side_effecting, schemas_for
from agent.orchestrator.usage_ledger import UsageLedger


ToolFn = Callable[..., dict[str, Any]]


@dataclass
class ToolLoopResult:
    assistant_text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    openai_called: bool = False
    error: str | None = None
    model: str | None = None
    used_fallback: bool = False
    fallback_reason: str | None = None
    rounds: int = 0
    estimated_cost_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    envelopes: list[dict[str, Any]] = field(default_factory=list)


def _usage_tokens(response: Any) -> tuple[int, int]:
    usage = getattr(response, "usage", None)
    prompt = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(
        getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
    )
    return prompt, completion


def _estimate_cost(
    prompt_tokens: int,
    completion_tokens: int,
    *,
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    return (
        (max(0, prompt_tokens) / 1_000_000.0) * input_usd_per_million
        + (max(0, completion_tokens) / 1_000_000.0) * output_usd_per_million
    )


def _extract_text(response: Any) -> str:
    direct = str(getattr(response, "output_text", "") or "").strip()
    if direct:
        return direct
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        if item_type != "message":
            continue
        text = getattr(item, "text", None)
        if text:
            parts.append(str(text))
            continue
        content = getattr(item, "content", None) or (item.get("content") if isinstance(item, dict) else None)
        if isinstance(content, list):
            for block in content:
                block_text = getattr(block, "text", None) or (
                    block.get("text") if isinstance(block, dict) else None
                )
                if block_text:
                    parts.append(str(block_text))
        elif isinstance(content, str) and content.strip():
            parts.append(content.strip())
    return "\n".join(p.strip() for p in parts if str(p).strip()).strip()


def _function_calls(response: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        if item_type != "function_call":
            continue
        name = str(getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else "") or "")
        call_id = str(
            getattr(item, "call_id", None)
            or getattr(item, "id", None)
            or (item.get("call_id") if isinstance(item, dict) else "")
            or (item.get("id") if isinstance(item, dict) else "")
            or f"call_{name}_{len(found)}"
        )
        raw_args = getattr(item, "arguments", None) or (
            item.get("arguments") if isinstance(item, dict) else "{}"
        )
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
        except (TypeError, ValueError, json.JSONDecodeError):
            args = {}
        found.append({"name": name, "arguments": args, "call_id": call_id})
    return found


def run_tool_loop(
    *,
    transport: Any,
    tools: dict[str, ToolFn],
    all_schemas: list[dict[str, Any]],
    system: str,
    input_messages: list[dict[str, str]],
    model: str,
    ledger: UsageLedger,
    preferred_mode: str = "PAPER",
    live_armed: bool = False,
    max_rounds: int = 3,
    max_total_tools: int = 6,
    timeout_seconds: float = 20.0,
    input_usd_per_million: float = 0.15,
    output_usd_per_million: float = 0.60,
    idempotency_key: str | None = None,
) -> ToolLoopResult:
    """Execute a bounded Responses tool loop. Side-effect tools run sequentially."""
    started = time.monotonic()
    schemas = schemas_for(all_schemas, preferred_mode=preferred_mode, live_armed=live_armed)
    reservation = reserve_spend(ledger, model=model, idempotency_key=idempotency_key)
    if reservation.blocked:
        return ToolLoopResult(
            assistant_text="",
            error=reservation.reason,
            used_fallback=True,
            fallback_reason=reservation.reason,
            model=model,
        )

    result = ToolLoopResult(assistant_text="", model=model, openai_called=False)
    previous_response_id: str | None = None
    pending_outputs: list[dict[str, Any]] = []
    total_tools = 0
    executed_ids: set[str] = set()

    try:
        for round_idx in range(max(1, int(max_rounds))):
            if time.monotonic() - started > timeout_seconds:
                result.error = "llm_timeout"
                break
            result.rounds = round_idx + 1
            create_kwargs: dict[str, Any] = {
                "model": model,
                "tools": schemas,
                "timeout": timeout_seconds,
            }
            if previous_response_id and pending_outputs:
                create_kwargs["previous_response_id"] = previous_response_id
                create_kwargs["input"] = pending_outputs
            else:
                create_kwargs["input"] = [
                    {"role": "system", "content": system},
                    *input_messages,
                ]

            response = transport.create(**create_kwargs)
            result.openai_called = True
            previous_response_id = str(
                getattr(response, "id", None) or getattr(response, "response_id", None) or ""
            ) or previous_response_id

            p_tok, c_tok = _usage_tokens(response)
            result.prompt_tokens += p_tok
            result.completion_tokens += c_tok
            result.estimated_cost_usd += _estimate_cost(
                p_tok,
                c_tok,
                input_usd_per_million=input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            )

            calls = _function_calls(response)
            text = _extract_text(response)
            if text:
                result.assistant_text = text

            if not calls:
                break

            # Partition: run side-effecting tools sequentially; read-only can batch.
            pending_outputs = []
            read_batch: list[dict[str, Any]] = []
            write_batch: list[dict[str, Any]] = []
            for call in calls:
                if total_tools >= max_total_tools:
                    break
                if call["call_id"] in executed_ids:
                    continue
                if is_side_effecting(call["name"]):
                    write_batch.append(call)
                else:
                    read_batch.append(call)

            def _run_one(call: dict[str, Any]) -> None:
                nonlocal total_tools
                name = call["name"]
                args = call["arguments"] if isinstance(call["arguments"], dict) else {}
                call_id = call["call_id"]
                if call_id in executed_ids:
                    return
                if total_tools >= max_total_tools:
                    return
                executed_ids.add(call_id)
                total_tools += 1
                t0 = time.monotonic()
                invalid = validate_tool_call(name, args)
                if invalid:
                    envelope = wrap_tool_result(name, {}, call_id=call_id, error=invalid)
                    entry = {"name": name, "error": invalid, "call_id": call_id}
                    result.tool_calls.append(entry)
                    result.envelopes.append(envelope.to_public())
                    pending_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps({"error": invalid}),
                        }
                    )
                    return
                # Mode-scoped: refuse live mutation if schema filter somehow missed.
                from agent.orchestrator.tool_registry import LIVE_MUTATION_TOOLS

                mode = "LIVE" if str(preferred_mode).upper() == "LIVE" else "PAPER"
                if name in LIVE_MUTATION_TOOLS and not (mode == "LIVE" and live_armed):
                    envelope = wrap_tool_result(name, {}, call_id=call_id, error="tool_not_allowed")
                    result.tool_calls.append({"name": name, "error": "tool_not_allowed", "call_id": call_id})
                    result.envelopes.append(envelope.to_public())
                    pending_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps({"error": "tool_not_allowed"}),
                        }
                    )
                    return
                # Empty live approve id from model is not authority.
                if name == "approve_live_trade" and not str(args.get("proposal_id") or "").strip():
                    envelope = wrap_tool_result(
                        name,
                        {
                            "ok": False,
                            "summary": (
                                "Live Approve requires an explicit proposal id (ltp_…). "
                                "Empty proposal_id is not authority to approve the latest order."
                            ),
                        },
                        call_id=call_id,
                    )
                    result.tool_calls.append(
                        {"name": name, "result": redact(envelope.verified), "call_id": call_id}
                    )
                    result.envelopes.append(envelope.to_public())
                    pending_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(redact(envelope.verified)),
                        }
                    )
                    return
                tool = tools.get(name)
                if tool is None:
                    envelope = wrap_tool_result(name, {}, call_id=call_id, error="tool_not_allowed")
                    result.tool_calls.append({"name": name, "error": "tool_not_allowed", "call_id": call_id})
                    result.envelopes.append(envelope.to_public())
                    pending_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps({"error": "tool_not_allowed"}),
                        }
                    )
                    return
                try:
                    raw = tool(**args)
                except TypeError:
                    envelope = wrap_tool_result(name, {}, call_id=call_id, error="tool_arguments_invalid")
                    result.tool_calls.append(
                        {"name": name, "error": "tool_arguments_invalid", "call_id": call_id}
                    )
                    result.envelopes.append(envelope.to_public())
                    pending_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps({"error": "tool_arguments_invalid"}),
                        }
                    )
                    return
                except Exception as exc:  # noqa: BLE001
                    envelope = wrap_tool_result(
                        name, {}, call_id=call_id, error=type(exc).__name__, duration_ms=int((time.monotonic() - t0) * 1000)
                    )
                    result.tool_calls.append(
                        {"name": name, "error": type(exc).__name__, "call_id": call_id}
                    )
                    result.envelopes.append(envelope.to_public())
                    pending_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps({"error": type(exc).__name__}),
                        }
                    )
                    return
                duration_ms = int((time.monotonic() - t0) * 1000)
                safe = redact(raw) if isinstance(raw, dict) else {"result": redact(raw)}
                envelope = wrap_tool_result(name, safe, call_id=call_id, duration_ms=duration_ms)
                result.tool_calls.append({"name": name, "result": safe, "call_id": call_id})
                result.envelopes.append(envelope.to_public())
                pending_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call_id,
                        "output": json.dumps(safe),
                    }
                )

            for call in read_batch:
                _run_one(call)
            for call in write_batch:
                _run_one(call)

            if not pending_outputs:
                break
            # Continue loop to synthesize with function_call_output.
        else:
            pass

        commit_spend(
            ledger,
            reservation,
            actual_usd=result.estimated_cost_usd,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            model=model,
        )
        return result
    except TimeoutError:
        release_spend(ledger, reservation)
        result.error = "llm_timeout"
        result.used_fallback = True
        result.fallback_reason = "llm_timeout"
        return result
    except Exception as exc:  # noqa: BLE001
        release_spend(ledger, reservation)
        result.error = "llm_unavailable"
        result.used_fallback = True
        result.fallback_reason = type(exc).__name__
        return result
