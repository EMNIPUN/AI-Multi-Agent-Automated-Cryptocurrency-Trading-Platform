"""OpenAI Responses API adapter for the orchestrator.

Default off. Dual gates required before any paid call.
Never places orders. Never changes risk or execution mode.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from agent.orchestrator.guard import ALLOWED_TOOLS, redact, validate_tool_call
from agent.orchestrator.service import LocalPlanner, PlannedCall
from agent.orchestrator.usage_ledger import UsageLedger


_DOTENV_LOADED = False


def _ensure_dotenv() -> None:
    """Load repo `.env` into os.environ once (does not override existing vars).

    Pydantic ApiSettings reads `.env` for its own fields only; orchestrator gates
    use os.getenv and need an explicit load for API/worker processes.
    """
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    try:
        from pathlib import Path

        from dotenv import load_dotenv
    except ImportError:
        _DOTENV_LOADED = True
        return
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)
    _DOTENV_LOADED = True


def _env_bool(name: str, default: bool = False) -> bool:
    _ensure_dotenv()
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    _ensure_dotenv()
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    _ensure_dotenv()
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "supervisor_status",
        "description": "Read paper supervisor state. Never places an order.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "paper_report",
        "description": "Read paper journal equity and positions.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "supervisor_command",
        "description": "Paper supervisor command: start, pause, resume, stop, or halt.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": ["start", "pause", "resume", "stop", "halt"],
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "analyze_symbol",
        "description": "Run the deterministic paper signal pipeline on public candles.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
                "interval": {"type": "string"},
            },
            # Responses API strict tools require every property key in `required`.
            "required": ["symbol", "category", "interval"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "run_full_analysis",
        "description": (
            "Run the full multi-agent analysis spine "
            "(market, technical, strategy, news advisory, risk, feasibility). "
            "Never places an exchange order."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
                "interval": {"type": "string"},
            },
            "required": ["symbol", "category", "interval"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "agent_status",
        "description": "List registered agents and Orchestrator/PAPER mode health.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "get_market_price",
        "description": (
            "Market Data Agent: fetch the current public Bybit last price for a symbol. "
            "Use for price/quote questions (HYPE, BNB, BTC, etc.). "
            "Does not analyze trades or place orders. Prefer category=linear for USDT perpetuals."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
            },
            "required": ["symbol", "category"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_market_quotes",
        "description": (
            "List symbols the Market Data Agent can quote. "
            "Use when the user asks which quotes/symbols are available."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "openai_usage",
        "description": "Show OpenAI orchestrator spend and gate status.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "live_readiness",
        "description": "Show LIVE readiness checklist. Does not authorize live trading.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "hype_feasibility",
        "description": "Evaluate whether 5 USDT / 1% risk can trade HYPEUSDT.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "propose_paper_trade",
        "description": (
            "Run the full multi-agent stack and propose a PAPER trade with entry, "
            "stop loss, and take profit. Does not place an order until approve_paper_trade."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
                "interval": {"type": "string"},
            },
            "required": ["symbol", "category", "interval"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "approve_paper_trade",
        "description": (
            "After human approval, place the pending PAPER (simulated) order. "
            "Never places a Bybit live or testnet order."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
            },
            "required": ["proposal_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "reject_paper_trade",
        "description": "Reject a pending PAPER trade proposal. No order is sent.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
            },
            "required": ["proposal_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "propose_live_trade",
        "description": (
            "Run the full multi-agent stack and propose a MAINNET LIVE trade "
            "(real money). Does not place an order until approve_live_trade."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
                "interval": {"type": "string"},
            },
            "required": ["symbol", "category", "interval"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "approve_live_trade",
        "description": (
            "After explicit human Approve in chat, place the pending MAINNET "
            "Bybit order. Requires AGENT_ALLOW_LIVE + MAINNET_TRADING_ENABLED."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
            },
            "required": ["proposal_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "reject_live_trade",
        "description": "Reject a pending LIVE trade proposal. No Bybit order is sent.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "proposal_id": {"type": "string"},
            },
            "required": ["proposal_id"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "propose_live_close",
        "description": (
            "Propose closing the current Bybit MAINNET position (or cancel resting order if flat). "
            "Does not send until approve_live_trade."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
            },
            "required": ["symbol", "category"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "propose_live_cancel_orders",
        "description": (
            "Propose cancelling resting Bybit MAINNET open orders for a symbol. "
            "Does not cancel until approve_live_trade."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
            },
            "required": ["symbol", "category"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "list_live_positions",
        "description": "Show Bybit MAINNET open position and resting orders for a symbol. Read-only.",
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
            },
            "required": ["symbol", "category"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "start_futures_intake",
        "description": (
            "Start gathering futures order details (side, Market/Limit, qty, leverage, SL/TP) "
            "before creating a MAINNET proposal. Pass the user message so partial answers are parsed."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"},
                "category": {"type": "string", "enum": ["linear", "spot"]},
                "message": {"type": "string"},
            },
            "required": ["symbol", "category", "message"],
            "additionalProperties": False,
        },
    },
    {
        "type": "function",
        "name": "continue_futures_intake",
        "description": (
            "Continue an active futures intake with the user's next answers "
            "(e.g. Buy Market qty 0.74 leverage 5 skip sl skip tp)."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
            "additionalProperties": False,
        },
    },
]


@dataclass(frozen=True)
class OrchestratorOpenAiConfig:
    enabled: bool = False
    spend_approved: bool = False
    api_key: str = ""
    model: str = ""
    timeout_seconds: float = 20.0
    max_retries: int = 1
    max_tool_loops: int = 3
    daily_budget_usd: float = 1.0
    monthly_budget_usd: float = 10.0
    input_usd_per_million: float = 5.0
    output_usd_per_million: float = 15.0
    ledger_path: str = "data/orchestrator_usage/usage.sqlite3"

    @classmethod
    def from_env(cls) -> OrchestratorOpenAiConfig:
        return cls(
            enabled=_env_bool("ORCHESTRATOR_OPENAI_ENABLED", False),
            spend_approved=_env_bool("ORCHESTRATOR_OPENAI_SPEND_APPROVED", False),
            api_key=(os.getenv("OPENAI_API_KEY") or "").strip(),
            model=(os.getenv("CRYPTONOVA_ORCHESTRATOR_MODEL") or os.getenv("OPENAI_MODEL") or "").strip(),
            timeout_seconds=max(1.0, _env_float("CRYPTONOVA_ORCHESTRATOR_TIMEOUT_SECONDS", 20.0)),
            max_retries=max(0, _env_int("CRYPTONOVA_ORCHESTRATOR_MAX_RETRIES", 1)),
            max_tool_loops=max(1, _env_int("CRYPTONOVA_ORCHESTRATOR_MAX_TOOL_LOOPS", 3)),
            daily_budget_usd=max(0.0, _env_float("CRYPTONOVA_ORCHESTRATOR_DAILY_BUDGET_USD", 1.0)),
            monthly_budget_usd=max(0.0, _env_float("CRYPTONOVA_ORCHESTRATOR_MONTHLY_BUDGET_USD", 10.0)),
            ledger_path=(
                os.getenv("CRYPTONOVA_ORCHESTRATOR_USAGE_LEDGER")
                or "data/orchestrator_usage/usage.sqlite3"
            ).strip(),
        )

    def gates_open(self) -> bool:
        return bool(self.enabled and self.spend_approved and self.api_key and self.model)

    def public_status(self, ledger: UsageLedger | None = None) -> dict[str, Any]:
        usage = ledger.summary() if ledger is not None else {"spent_usd_24h": 0.0, "spent_usd_30d": 0.0}
        return {
            "enabled": self.enabled,
            "spend_approved": self.spend_approved,
            "api_key_configured": bool(self.api_key),
            "model_configured": bool(self.model),
            "model": self.model or None,
            "gates_open": self.gates_open(),
            "daily_budget_usd": self.daily_budget_usd,
            "monthly_budget_usd": self.monthly_budget_usd,
            "spent_usd_24h": usage.get("spent_usd_24h", 0.0),
            "spent_usd_30d": usage.get("spent_usd_30d", 0.0),
            "places_orders": False,
            "live_orders": False,
            "llm_changed_decision": False,
            "paid_calls_blocked_until_spend_approval": not self.spend_approved,
        }


class ResponsesTransport(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class FakeResponsesTransport:
    """Deterministic fake Responses API. Never opens a network socket."""

    def __init__(
        self,
        planned: list[PlannedCall] | None = None,
        *,
        fail: str | None = None,
        output_text: str = "",
    ) -> None:
        self.planned = list(planned or [])
        self.fail = fail
        self.output_text = output_text
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(dict(kwargs))
        if self.fail == "timeout":
            raise TimeoutError("openai_timeout")
        if self.fail == "rate_limit":
            raise RuntimeError("Rate limit 429")
        if self.fail:
            raise RuntimeError(self.fail)
        output: list[Any] = []
        for call in self.planned:
            output.append(
                _FakeItem(
                    type="function_call",
                    name=call.name,
                    arguments=json.dumps(call.arguments),
                    call_id=f"call_{call.name}",
                )
            )
        text = self.output_text.strip()
        if text:
            output.append(_FakeItem(type="message", text=text))
        elif not output:
            output.append(_FakeItem(type="message", text="status only"))
        return _FakeResponse(
            output=output,
            model=str(kwargs.get("model") or ""),
            usage=_FakeUsage(),
            output_text=text,
        )


@dataclass
class _FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 5


@dataclass
class _FakeItem:
    type: str
    name: str = ""
    arguments: str = "{}"
    call_id: str = ""
    text: str = ""


@dataclass
class _FakeResponse:
    output: list[Any]
    model: str
    usage: _FakeUsage
    output_text: str = ""


def estimate_cost_usd(
    *,
    prompt_tokens: int,
    completion_tokens: int,
    input_usd_per_million: float,
    output_usd_per_million: float,
) -> float:
    return (
        (max(0, prompt_tokens) / 1_000_000.0) * input_usd_per_million
        + (max(0, completion_tokens) / 1_000_000.0) * output_usd_per_million
    )


def _default_client_factory(*, api_key: str, timeout: float) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover — environment specific
        raise RuntimeError("openai_sdk_unavailable") from exc
    return OpenAI(api_key=api_key, timeout=timeout)


def _extract_assistant_text(response: Any) -> str:
    """Pull natural-language text from a Responses API result."""
    direct = str(getattr(response, "output_text", "") or "").strip()
    if direct:
        return direct
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        if item_type == "message":
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
        elif item_type is None and getattr(item, "text", None):
            parts.append(str(item.text))
    return "\n".join(part.strip() for part in parts if str(part).strip()).strip()


class OpenAiOrchestratorPlanner:
    """Plans tool calls via Responses API. Falls back to LocalPlanner on gate/budget failure."""

    def __init__(
        self,
        config: OrchestratorOpenAiConfig | None = None,
        *,
        transport: ResponsesTransport | None = None,
        ledger: UsageLedger | None = None,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config or OrchestratorOpenAiConfig.from_env()
        self.ledger = ledger or UsageLedger(self.config.ledger_path)
        self._transport = transport
        self._client_factory = client_factory or _default_client_factory
        self.last_openai_called = False
        self.last_error: str | None = None
        self.last_assistant_text: str | None = None

    def plan(self, message: str, *, preferred_mode: str = "PAPER") -> list[PlannedCall]:
        mode = "LIVE" if str(preferred_mode or "").strip().upper() == "LIVE" else "PAPER"
        self.last_openai_called = False
        self.last_error = None
        self.last_assistant_text = None
        if not self.config.gates_open():
            self.last_error = "openai_spend_gate_closed"
            return LocalPlanner().plan(message, preferred_mode=mode)
        now_ms = int(time.time() * 1000)
        spent_day = self.ledger.spent_since_ms(now_ms - 86_400_000)
        spent_month = self.ledger.spent_since_ms(now_ms - 30 * 86_400_000)
        if spent_day >= self.config.daily_budget_usd:
            self.last_error = "daily_budget_exceeded"
            return LocalPlanner().plan(message, preferred_mode=mode)
        if spent_month >= self.config.monthly_budget_usd:
            self.last_error = "monthly_budget_exceeded"
            return LocalPlanner().plan(message, preferred_mode=mode)

        # Greetings are chat-only: return OpenAI prose, not the status template card.
        from agent.orchestrator.service import is_greeting

        chat_only = is_greeting(message)
        # Deterministic market/analysis routes beat OpenAI tool guessing (BNB price,
        # available quotes, entry/TP/SL, run all agents, place paper trade).
        if not chat_only:
            routed = LocalPlanner().route(message, preferred_mode=mode)
            if routed is not None:
                return routed
        attempts = 0
        last_exc: Exception | None = None
        while attempts <= self.config.max_retries:
            attempts += 1
            try:
                planned = self._call_model(message, chat_only=chat_only, preferred_mode=mode)
                self.last_openai_called = True
                return planned
            except TimeoutError as exc:
                last_exc = exc
                self.last_error = "llm_timeout"
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                name = type(exc).__name__.lower()
                text = str(exc).lower()
                if "429" in text or "rate" in text:
                    self.last_error = "rate_limit"
                else:
                    self.last_error = "llm_unavailable"
                if "timeout" in name or "timeout" in text:
                    self.last_error = "llm_timeout"
        if last_exc is not None and self.last_error == "llm_timeout":
            raise TimeoutError("llm_timeout") from last_exc
        return LocalPlanner().plan(message, preferred_mode=mode)

    def _call_model(
        self,
        message: str,
        *,
        chat_only: bool = False,
        preferred_mode: str = "PAPER",
    ) -> list[PlannedCall]:
        mode = "LIVE" if str(preferred_mode or "").strip().upper() == "LIVE" else "PAPER"
        transport = self._transport
        if transport is None:
            client = self._client_factory(api_key=self.config.api_key, timeout=self.config.timeout_seconds)
            transport = client.responses
        if chat_only:
            system = (
                "You are CryptoNova's Orchestrator chat assistant. "
                "Reply naturally and briefly like ChatGPT. "
                f"The operator chat mode is {mode}. "
                "PAPER = simulated journal. LIVE = Bybit MAINNET with per-order Approve. "
                "Do not claim you placed an exchange order without Approve. "
                "Do not dump a raw status dashboard unless the user asks for status."
            )
            create_kwargs: dict[str, Any] = {
                "model": self.config.model,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                "timeout": self.config.timeout_seconds,
            }
        else:
            mode_bias = (
                "Operator chat mode is LIVE: for open/close orders use start_futures_intake / "
                "propose_live_close / list_live_positions / approve_live_trade. "
                "If the user asks for analysis, plan, or report FIRST, call run_full_analysis "
                "before any order intake — even in LIVE mode. "
                "Use propose_paper_trade only when the user explicitly says paper."
                if mode == "LIVE"
                else "Operator chat mode is PAPER: prefer propose_paper_trade and paper_report. "
                "Use live/Bybit tools only when the user explicitly asks for live/Bybit/close on exchange."
            )
            system = (
                "You are CryptoNova's trading orchestrator. Reply helpfully and specifically. "
                f"{mode_bias} "
                "Price questions (HYPE/BNB/BTC/...): call get_market_price with SYMBOLUSDT and category=linear. "
                "Available quotes/symbols: call list_market_quotes. "
                "Requests for technical analysis, entry, TP, stop loss, timing, plan, full report, "
                "or run all agents: call run_full_analysis with the named symbol "
                "(BTC→BTCUSDT, HYPE→HYPEUSDT; default linear 15). "
                "Do NOT start_futures_intake when the user asks for analysis/plan/report first. "
                "User wants to CLOSE/exit/flat a live Bybit position or close current order: "
                "call propose_live_close (default HYPEUSDT linear). NOT run_full_analysis. "
                "User wants to cancel resting Bybit open orders: call propose_live_cancel_orders. "
                "User asks what position is open on Bybit: call list_live_positions. "
                "After analysis, if user says place the order / use my Bybit / have X USDT / use that: "
                "call start_futures_intake (NOT approve_live_trade — there is no proposal yet). "
                "User is ready to OPEN a LIVE/mainnet/futures trade (has side/qty intent, not just analysis): "
                "call start_futures_intake (collects side, Market/Limit, qty, leverage, optional SL/TP; then Approve). "
                "When futures intake is already active: ALWAYS call continue_futures_intake "
                "(including for Place order / Place the order / field answers / Approve before checklist is done). "
                "Never restart intake or ask vague clarifying questions while a checklist is open. "
                "Only call approve_live_trade after a pending proposal exists (ltp_… / Approve UI). "
                "User wants a paper/simulated trade: call propose_paper_trade. "
                "If unsure and user just says trade with no analysis request: "
                "LIVE mode → start_futures_intake; PAPER mode → propose_paper_trade. "
                "User says approve/confirm live trade/close: call approve_live_trade "
                "(proposal_id ltp_… or empty string for latest). "
                "User says approve/confirm paper trade: call approve_paper_trade "
                "(proposal_id ptp_… or empty string for latest). "
                "User says reject live proposal: call reject_live_trade. "
                "User says reject paper: call reject_paper_trade. "
                "Do not call agent_status for close/open Bybit order requests. "
                "Every LIVE order needs explicit chat Approve — never skip approval. "
                "Never raise leverage or change env execution flags from chat."
            )
            create_kwargs = {
                "model": self.config.model,
                "tools": TOOL_SCHEMAS,
                "input": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": message},
                ],
                "timeout": self.config.timeout_seconds,
            }
        response = transport.create(**create_kwargs)
        usage = getattr(response, "usage", None)
        prompt_tokens = int(getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(
            getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
        )
        cost = estimate_cost_usd(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            input_usd_per_million=self.config.input_usd_per_million,
            output_usd_per_million=self.config.output_usd_per_million,
        )
        self.ledger.record(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost,
            model=self.config.model,
        )
        self.last_assistant_text = _extract_assistant_text(response) or None
        if chat_only:
            return []
        planned: list[PlannedCall] = []
        for item in getattr(response, "output", []) or []:
            item_type = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
            if item_type != "function_call":
                continue
            name = str(getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else "") or "")
            raw_args = getattr(item, "arguments", None) or (item.get("arguments") if isinstance(item, dict) else "{}")
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args or {})
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if name not in ALLOWED_TOOLS:
                continue
            if validate_tool_call(name, args):
                continue
            planned.append(PlannedCall(name=name, arguments=redact(args) if isinstance(args, dict) else {}))
            if len(planned) >= self.config.max_tool_loops:
                break
        if planned:
            return planned
        if self.last_assistant_text:
            return []
        return LocalPlanner().plan(message, preferred_mode=mode)
