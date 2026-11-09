"""Deterministic orchestrator. Paid OpenAI stays gated; LIVE needs chat Approve."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.orchestrator.guard import injection_refusal, redact, validate_tool_call
from agent.orchestrator.live_authorization import refuse_live_escalation


Tool = Callable[..., dict[str, Any]]


@dataclass
class PlannedCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _live_env_armed() -> bool:
    """True when operator env arms MAINNET live (Approve still required per order)."""
    if _flag("BYBIT_TESTNET") or _flag("BYBIT_DEMO"):
        return False
    return _flag("AGENT_ALLOW_LIVE") and _flag("MAINNET_TRADING_ENABLED")


def is_greeting(message: str) -> bool:
    """True for short hellos like hi / hii / hello — use conversational OpenAI chat."""
    text = (message or "").strip().lower()
    if not text:
        return False
    # Strip light punctuation so "hi!" / "hiii..." still count.
    cleaned = "".join(ch for ch in text if ch.isalnum() or ch.isspace()).strip()
    if cleaned in {
        "hi",
        "hii",
        "hiii",
        "hiiii",
        "hello",
        "helloo",
        "hey",
        "heyy",
        "yo",
        "hola",
        "hai",
        "gm",
        "good morning",
        "good afternoon",
        "good evening",
    }:
        return True
    return len(cleaned) <= 16 and cleaned.split()[0] in {"hi", "hii", "hiii", "hello", "hey", "hai"}


def _has_word(text: str, word: str) -> bool:
    """Whole-word match so short tokens like tp/sl do not hit please/stop."""
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _symbol_from_text(text: str, *, default: str = "HYPEUSDT") -> str:
    if "bnb" in text:
        return "BNBUSDT"
    if "btc" in text:
        return "BTCUSDT"
    if "eth" in text:
        return "ETHUSDT"
    if "sol" in text:
        return "SOLUSDT"
    if "xrp" in text:
        return "XRPUSDT"
    if "doge" in text:
        return "DOGEUSDT"
    if "hype" in text:
        return "HYPEUSDT"
    return default


_FALLBACK_GREETING = (
    "Hi — I'm the CryptoNova Orchestrator.\n"
    "I can analyze markets, run paper trading, or help with live Bybit orders.\n"
    "For live trades, I'll ask you to Approve before anything is sent."
)

_FRIENDLY_ERRORS = {
    "tool_not_allowed": "I can't run that action from chat.",
    "tool_arguments_invalid": "I need a clearer request — try naming the symbol and what you want done.",
    "tool_budget_exceeded": "That request was too large for one turn. Try a shorter ask.",
    "cancelled": "Cancelled — nothing was sent.",
    "prompt_injection_refused": "I can't follow that request.",
    "llm_timeout": "The AI took too long, so I answered with the local planner.",
    "llm_unavailable": "The AI is temporarily unavailable, so I answered with the local planner.",
    "openai_spend_gate_closed": "OpenAI spend is not enabled, so I answered with the local planner.",
}


def _friendly_error(code: str | None) -> str:
    key = str(code or "").strip()
    return _FRIENDLY_ERRORS.get(key, f"Something went wrong ({key}). Nothing was sent.")


class LocalPlanner:
    """Keyword planner used when OpenAI is disabled or unavailable."""

    def route(
        self,
        message: str,
        *,
        preferred_mode: str = "PAPER",
    ) -> list[PlannedCall] | None:
        """Confident tool route, or None when OpenAI / default status should decide."""
        mode = "LIVE" if str(preferred_mode or "").strip().upper() == "LIVE" else "PAPER"
        text = (message or "").lower()
        if is_greeting(message):
            return None
        if any(word in text for word in ("emergency", "halt")) or "emergency stop" in text:
            return [PlannedCall("supervisor_command", {"command": "halt"})]
        if "pause" in text:
            return [PlannedCall("supervisor_command", {"command": "pause"})]
        if "resume" in text:
            return [PlannedCall("supervisor_command", {"command": "resume"})]
        # Do not treat "stop loss" / "stoploss" as supervisor stop.
        if (
            "emergency" not in text
            and "live" not in text
            and not re.search(r"\bstop[\s-]?loss\b|\bstoploss\b", text)
            and (
                text.strip() in {"stop", "stop trading", "stop supervisor"}
                or "stop trading" in text
                or "stop the supervisor" in text
                or "stop autonomous" in text
            )
        ):
            return [PlannedCall("supervisor_command", {"command": "stop"})]
        # Avoid matching negations like "do not start trading".
        if "live" not in text and not any(
            neg in text for neg in ("do not start", "don't start", "dont start", "never start")
        ):
            if (
                ("start" in text and ("paper" in text or "autonomous" in text))
                or "start autonomous" in text
                or "start trading" in text
            ):
                return [PlannedCall("supervisor_command", {"command": "start"})]
        if any(word in text for word in ("usage", "openai cost", "spend", "token budget")):
            return [PlannedCall("openai_usage", {})]
        if any(
            word in text
            for word in ("readiness", "live checklist", "live ready", "authorization workflow")
        ):
            return [PlannedCall("live_readiness", {})]
        # Which symbols can be quoted?
        if any(
            phrase in text
            for phrase in (
                "available quote",
                "available quotes",
                "avialbe quote",
                "avaliable quote",
                "which quote",
                "what quote",
                "supported symbol",
                "supported symbols",
                "list symbol",
                "list symbols",
            )
        ):
            return [PlannedCall("list_market_quotes", {})]
        # Human approval / reject of a pending PAPER or LIVE proposal.
        live_proposal_match = re.search(r"\b(ltp_[a-f0-9]{8,32})\b", text)
        paper_proposal_match = re.search(r"\b(ptp_[a-f0-9]{8,32})\b", text)
        live_proposal_id = live_proposal_match.group(1) if live_proposal_match else ""
        paper_proposal_id = paper_proposal_match.group(1) if paper_proposal_match else ""
        # Typo-tolerant approve tokens (aprove / apprve / aprrove).
        approve_typo = bool(re.fullmatch(r"a+p+r+o*v+e+d?", text.strip()))
        explicit_approve = approve_typo or any(
            phrase in text
            for phrase in (
                "approve live",
                "approve the live",
                "approve paper",
                "approve trade",
                "approve the trade",
                "approve the paper",
                "confirm live",
                "confirm paper",
                "confirm trade",
                "execute live",
                "execute paper",
            )
        ) or (text.strip() in {"approve", "approved", "confirm", "yes", "aprove", "apprve"})
        # "place it / place the order" only means Approve when a proposal id is present
        # or the message is a short confirm — otherwise it means start order intake.
        confirm_place_only = any(
            phrase in text
            for phrase in (
                "yes place",
                "yes, place",
                "place it",
            )
        ) and len(text.split()) <= 6
        approve_live = (
            any(
                phrase in text
                for phrase in (
                    "approve live",
                    "approve the live",
                    "confirm live",
                    "execute live",
                )
            )
            or bool(live_proposal_id)
            or (
                explicit_approve
                and "paper" not in text
                and (mode == "LIVE" or _live_env_armed())
            )
        )
        approve_any = explicit_approve or confirm_place_only or bool(live_proposal_id or paper_proposal_id)
        # Approve before checklist is complete → continue intake prompt, not empty approve.
        if approve_any or approve_live:
            from agent.orchestrator.futures_intake import get_active_intake
            from agent.orchestrator.live_trade_proposals import (
                get_live_proposal,
                latest_pending_live_proposal,
            )

            pending = (
                get_live_proposal(live_proposal_id)
                if live_proposal_id
                else latest_pending_live_proposal()
            )
            intake = get_active_intake()
            if pending is None and intake is not None and not live_proposal_id:
                return [PlannedCall("continue_futures_intake", {"message": message})]
        if approve_live or (approve_any and live_proposal_id):
            return [PlannedCall("approve_live_trade", {"proposal_id": live_proposal_id})]
        if approve_any and "paper" in text:
            return [PlannedCall("approve_paper_trade", {"proposal_id": paper_proposal_id})]
        if approve_any and not paper_proposal_id and (mode == "LIVE" or _live_env_armed()):
            # Prefer live approve in LIVE chat mode (or when MAINNET is armed).
            return [PlannedCall("approve_live_trade", {"proposal_id": ""})]
        if approve_any:
            return [PlannedCall("approve_paper_trade", {"proposal_id": paper_proposal_id})]
        reject_live = any(
            phrase in text
            for phrase in (
                "reject live",
                "reject the live",
                "cancel live",
            )
        ) or bool(live_proposal_id and any(w in text for w in ("reject", "cancel")))
        if reject_live:
            return [PlannedCall("reject_live_trade", {"proposal_id": live_proposal_id})]
        if any(
            phrase in text
            for phrase in (
                "reject paper",
                "reject trade",
                "reject the trade",
                "cancel paper",
                "cancel trade",
                "don't place",
                "do not place",
            )
        ) or (text.strip() in {"reject", "cancel", "no"}):
            if mode == "LIVE" and not paper_proposal_id:
                return [PlannedCall("reject_live_trade", {"proposal_id": live_proposal_id})]
            return [PlannedCall("reject_paper_trade", {"proposal_id": paper_proposal_id})]
        # Close / cancel existing Bybit position or resting orders (Approve required).
        wants_close = any(
            phrase in text
            for phrase in (
                "close current",
                "close the",
                "close my",
                "close position",
                "close order",
                "close open",
                "close hype",
                "close btc",
                "close eth",
                "i want close",
                "want to close",
                "want close",
                "flat position",
                "exit position",
                "exit the position",
                "close on bybit",
                "close inside bybit",
            )
        ) or (
            "close" in text
            and any(w in text for w in ("order", "position", "bybit", "live", "hype", "btc", "eth"))
        )
        wants_cancel_orders = any(
            phrase in text
            for phrase in (
                "cancel open order",
                "cancel open orders",
                "cancel resting",
                "cancel bybit order",
                "cancel the order",
            )
        )
        wants_list_positions = "paper" not in text and any(
            phrase in text
            for phrase in (
                "list position",
                "list positions",
                "show position",
                "show positions",
                "my bybit position",
                "bybit position",
                "what position on bybit",
                "live position",
                "positions on bybit",
            )
        )
        if wants_cancel_orders:
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            return [PlannedCall("propose_live_cancel_orders", {"symbol": symbol, "category": "linear"})]
        if wants_close:
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            return [PlannedCall("propose_live_close", {"symbol": symbol, "category": "linear"})]
        if wants_list_positions:
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            return [PlannedCall("list_live_positions", {"symbol": symbol, "category": "linear"})]
        # Explicit trade intent → proposal (LIVE when armed, else PAPER); always needs Approve.
        wants_live = any(
            phrase in text
            for phrase in (
                "live trade",
                "propose live",
                "mainnet trade",
                "real money",
                "place a live",
                "bybit live",
                "open live",
                "open a live",
                "my bybit",
                "bybit account",
                "use my bybit",
                "use bybit",
            )
        )
        wants_trade = any(
            phrase in text
            for phrase in (
                "i want trade",
                "want to trade",
                "want trade",
                "place the trade",
                "place trade",
                "place a trade",
                "place the order",
                "place order",
                "can place",
                "put trade",
                "open a trade",
                "open trade",
                "enter trade",
                "make a trade",
                "trade hype",
                "trade btc",
                "trade eth",
                "propose trade",
                "paper trade",
                "use that",
                "go ahead and trade",
                "go ahead place",
            )
        ) or wants_live or (
            "usdt" in text
            and any(w in text for w in ("have", "with", "use", "balance", "capital", "bybit"))
        )
        wants_futures_intake = any(
            phrase in text
            for phrase in (
                "futures order",
                "place futures",
                "open futures",
                "futures trade",
                "gather order",
                "order details",
                "limit order",
                "market order",
                "set leverage",
                "place order",
                "place the order",
                "live order",
            )
        )
        from agent.orchestrator.futures_intake import (
            clear_intake,
            get_active_intake,
            is_place_order_confirm,
            looks_like_intake_answer,
        )

        # Checklist replies (Buy Market qty … skip sl skip tp) are order fields, not analysis.
        order_fill_message = looks_like_intake_answer(text) and any(
            tok in text
            for tok in (
                "buy",
                "sell",
                "long",
                "short",
                "qty",
                "quantity",
                "leverage",
                "market",
                "limit",
                "skip sl",
                "skip tp",
                "usdt",
            )
        )

        # Full analysis / entry / TP / SL / timing — before agent_status ("all agents").
        # Do not treat intake field answers (skip sl / tp 73 / qty …) as analysis asks.
        # "put/place trade proper time" is a trade request, not analyze-only.
        trade_with_timing = (
            "proper time" in text or ("timing" in text and "trade" in text)
        ) and any(
            phrase in text
            for phrase in (
                "put trade",
                "place trade",
                "place the trade",
                "place a trade",
                "want trade",
                "want to trade",
                "i want trade",
                "trade hype",
                "trade btc",
                "trade eth",
            )
        )
        wants_levels = (not order_fill_message) and (not trade_with_timing) and (
            any(
                phrase in text
                for phrase in (
                    "entry",
                    "take profit",
                    "take-profit",
                    "stop loss",
                    "stop-loss",
                    "lost price",
                    "loss price",
                    "proper time",
                    "timing",
                    "technical",
                )
            )
            or _has_word(text, "tp")
            or _has_word(text, "sl")
        )
        wants_registry_only = any(
            phrase in text
            for phrase in (
                "agent status",
                "list agents",
                "show agents",
                "show all agents",
                "registered agents",
                "multi-agent status",
            )
        )
        wants_all_agents = (not wants_registry_only) and any(
            phrase in text
            for phrase in (
                "run all agent",
                "run all agents",
                "all agent",
                "all agents",
                "using all agents",
                "full analysis",
                "multi-agent",
                "all available agents",
            )
        )
        wants_market_analysis = (not order_fill_message) and (
            wants_levels
            or wants_all_agents
            or any(
                phrase in text
                for phrase in (
                    "analysis",
                    "analyse",
                    "analyze",
                    "full report",
                    "market report",
                    "trading plan",
                    "trade plan",
                    "give me plan",
                    "give my plan",
                    "give me a plan",
                    "firstly",
                    "first give",
                    "before decide",
                    "before i decide",
                    "before trading",
                    "before place",
                    "before open",
                    "before order",
                    "technical report",
                    "what should i do",
                    "should i buy",
                    "should i sell",
                )
            )
            or (
                "plan" in text
                and any(tok in text for tok in ("btc", "eth", "hype", "trade", "live", "market"))
            )
            or (
                "report" in text
                and any(
                    tok in text
                    for tok in ("btc", "eth", "hype", "sol", "full", "analysis", "market", "trade")
                )
            )
        )
        # Hard analysis asks may cancel an open checklist; soft questions do not.
        explicit_analysis_while_intake = any(
            phrase in text
            for phrase in (
                "full analysis",
                "full report",
                "run all agent",
                "run all agents",
                "analyze",
                "analyse",
                "analysis",
                "give me plan",
                "give my plan",
                "trading plan",
                "market report",
                "before decide",
                "before place",
                "before order",
                "firstly",
            )
        )

        active_intake = get_active_intake()
        # Open checklist wins: continue (don't restart) unless user clearly asks for a new analysis.
        # Keep short greetings conversational without wiping the checklist.
        if active_intake is not None:
            if wants_market_analysis and explicit_analysis_while_intake and not order_fill_message:
                clear_intake()
            elif is_greeting(message):
                return None
            else:
                return [PlannedCall("continue_futures_intake", {"message": message})]

        # Analysis / plan first — even in LIVE mode, even if user also mentions trade.
        if wants_market_analysis:
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            return [
                PlannedCall(
                    "run_full_analysis",
                    {"symbol": symbol, "category": "linear", "interval": "15"},
                )
            ]

        # One-shot checklist in LIVE (or explicit futures intent) → start intake + parse fields.
        if order_fill_message and (mode == "LIVE" or wants_futures_intake or wants_live):
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            return [
                PlannedCall(
                    "start_futures_intake",
                    {"symbol": symbol, "category": "linear", "message": message},
                )
            ]

        if wants_trade or wants_futures_intake or is_place_order_confirm(message):
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            # Chat mode biases opens; explicit "paper" / "live" words still win.
            if "paper" in text and not wants_live:
                use_live = False
            elif wants_live or wants_futures_intake or mode == "LIVE" or is_place_order_confirm(message):
                use_live = True
            else:
                use_live = False
            if use_live:
                # LIVE futures: collect order type / leverage / qty before proposing.
                return [
                    PlannedCall(
                        "start_futures_intake",
                        {"symbol": symbol, "category": "linear", "message": message},
                    )
                ]
            return [
                PlannedCall(
                    "propose_paper_trade",
                    {"symbol": symbol, "category": "linear", "interval": "15"},
                )
            ]
        # Price/quote questions → Market Data Agent only (not trade analysis).
        if any(
            word in text
            for word in (
                "price",
                "quote",
                "ticker",
                "how much",
                "last price",
                "mark price",
                "whats the price",
                "what's the price",
            )
        ) or (
            ("price" in text or "now" in text)
            and any(tok in text for tok in ("hype", "btc", "eth", "sol", "bnb", "xrp", "doge"))
        ):
            symbol = _symbol_from_text(text, default="HYPEUSDT")
            return [PlannedCall("get_market_price", {"symbol": symbol, "category": "linear"})]
        if "feasibility" in text or "feasible" in text or ("risk budget" in text and "hype" in text):
            return [PlannedCall("hype_feasibility", {})]
        # Paper journal only — not market analysis reports.
        if any(
            word in text for word in ("pnl", "performance", "equity", "balance")
        ) or (
            "paper" in text and any(w in text for w in ("report", "result", "position"))
        ) or (
            any(word in text for word in ("report", "result", "position"))
            and "btc" not in text
            and "eth" not in text
            and "hype" not in text
            and "analysis" not in text
            and "live" not in text
        ):
            return [PlannedCall("paper_report", {})]
        if wants_registry_only or any(
            phrase in text
            for phrase in (
                "agent status",
                "list agents",
                "registered agents",
                "multi-agent status",
                "show agents",
                "show all agents",
            )
        ):
            return [PlannedCall("agent_status", {})]
        if any(word in text for word in ("status", "holding", "why", "supervisor")):
            return [PlannedCall("supervisor_status", {})]
        if "hype" in text or "analyze" in text or "evaluate" in text:
            symbol = "HYPEUSDT" if "hype" in text else "BTCUSDT"
            if "feasib" in text:
                return [PlannedCall("hype_feasibility", {})]
            if "agent" in text or "technical" in text:
                return [
                    PlannedCall(
                        "run_full_analysis",
                        {"symbol": symbol, "category": "linear", "interval": "15"},
                    )
                ]
            return [PlannedCall("analyze_symbol", {"symbol": symbol, "category": "linear", "interval": "15"})]
        return None

    def plan(self, message: str, *, preferred_mode: str = "PAPER") -> list[PlannedCall]:
        if is_greeting(message):
            return []
        routed = self.route(message, preferred_mode=preferred_mode)
        if routed is not None:
            return routed
        return [PlannedCall("supervisor_status", {})]


class FailingModel:
    """Test double: a paid model that is unavailable. The supervisor path still answers."""

    def plan(self, message: str) -> list[PlannedCall]:
        raise TimeoutError("llm_timeout")


def select_planner(model: Any | None = None) -> Any:
    """Prefer an injected model; otherwise LocalPlanner. OpenAI requires dual spend gates."""
    if model is not None:
        return model
    try:
        from agent.orchestrator.openai_adapter import OpenAiOrchestratorPlanner, OrchestratorOpenAiConfig

        config = OrchestratorOpenAiConfig.from_env()
        if config.gates_open():
            return OpenAiOrchestratorPlanner(config)
    except Exception:  # noqa: BLE001 — never block paper path on adapter import
        pass
    return LocalPlanner()


class Orchestrator:
    def __init__(
        self,
        tools: dict[str, Tool],
        *,
        model: Any | None = None,
        max_steps: int = 3,
    ) -> None:
        self.tools = tools
        self.model = select_planner(model)
        self.max_steps = max(1, int(max_steps))

    def handle(
        self,
        message: str,
        *,
        cancelled: bool = False,
        preferred_mode: str = "PAPER",
    ) -> dict[str, Any]:
        mode = "LIVE" if str(preferred_mode or "").strip().upper() == "LIVE" else "PAPER"
        if cancelled:
            return self._body(
                "cancelled",
                tool_calls=[],
                error="cancelled",
                openai_called=False,
                preferred_mode=mode,
            )
        refusal = injection_refusal(message)
        if refusal:
            return self._body(
                refusal,
                tool_calls=[],
                error=refusal,
                openai_called=False,
                preferred_mode=mode,
            )
        live_refusal = refuse_live_escalation(message)
        if live_refusal is not None:
            return self._body(
                str(live_refusal.get("summary") or "LIVE BLOCKED"),
                tool_calls=[{"name": "live_readiness", "result": redact(live_refusal)}],
                error="live_escalation_refused",
                openai_called=False,
                preferred_mode=mode,
            )
        openai_called = False
        assistant_text: str | None = None
        model_error: str | None = None
        # Prefer LocalPlanner whenever it is confident — OpenAI must not override
        # analysis / intake / approve into vague clarifications or the wrong tool.
        local_route = LocalPlanner().route(message, preferred_mode=mode)
        if local_route is not None:
            planned = list(local_route)
        else:
            try:
                plan_fn = self.model.plan
                try:
                    planned = list(plan_fn(message, preferred_mode=mode))
                except TypeError:
                    planned = list(plan_fn(message))
                model_error = getattr(self.model, "last_error", None)
                openai_called = bool(getattr(self.model, "last_openai_called", False))
                raw_assistant = getattr(self.model, "last_assistant_text", None)
                assistant_text = str(raw_assistant).strip() if raw_assistant else None
            except TimeoutError:
                planned = LocalPlanner().plan(message, preferred_mode=mode)
                model_error = "llm_timeout"
                openai_called = False
            except Exception:  # noqa: BLE001 — model failure must not authorize anything
                planned = LocalPlanner().plan(message, preferred_mode=mode)
                model_error = "llm_unavailable"
                openai_called = False
            # If OpenAI returned prose only while futures intake is open, keep the checklist moving.
            if not planned:
                try:
                    from agent.orchestrator.futures_intake import get_active_intake

                    if get_active_intake() is not None:
                        planned = [PlannedCall("continue_futures_intake", {"message": message})]
                        assistant_text = None
                except Exception:  # noqa: BLE001
                    pass
        calls: list[dict[str, Any]] = []
        for step, call in enumerate(planned, start=1):
            if step > self.max_steps:
                calls.append({"name": call.name, "error": "tool_budget_exceeded"})
                break
            invalid = validate_tool_call(call.name, call.arguments)
            if invalid:
                calls.append({"name": call.name, "error": invalid})
                continue
            tool = self.tools.get(call.name)
            if tool is None:
                calls.append({"name": call.name, "error": "tool_not_allowed"})
                continue
            try:
                result = tool(**call.arguments)
            except TypeError:
                calls.append({"name": call.name, "error": "tool_arguments_invalid"})
                continue
            calls.append({"name": call.name, "result": redact(result)})
        reply = self._reply(
            calls,
            model_error,
            message=message,
            assistant_text=assistant_text,
            preferred_mode=mode,
        )
        return self._body(
            reply,
            tool_calls=calls,
            error=model_error,
            openai_called=openai_called,
            preferred_mode=mode,
        )

    def _reply(
        self,
        calls: list[dict[str, Any]],
        model_error: str | None,
        *,
        message: str = "",
        assistant_text: str | None = None,
        preferred_mode: str = "PAPER",
    ) -> str:
        mode = "LIVE" if str(preferred_mode or "").upper() == "LIVE" else "PAPER"
        # Prefer tool summaries when tools ran. OpenAI prose is for chat-only turns.
        if assistant_text and assistant_text.strip() and not calls:
            return assistant_text.strip()
        if not calls:
            if is_greeting(message):
                return _FALLBACK_GREETING
            return (
                "Tell me what you'd like next — for example analyze HYPEUSDT, "
                "open a futures order, or close a Bybit position."
                if mode == "LIVE"
                else "Tell me what you'd like next — for example start paper trading, "
                "analyze HYPEUSDT, or switch to LIVE for Bybit orders."
            )
        last = calls[-1]
        if last.get("error"):
            return _friendly_error(str(last.get("error")))
        result = last.get("result") if isinstance(last.get("result"), dict) else {}
        summary = result.get("summary")
        if isinstance(summary, str) and summary.strip():
            text = summary.strip()
        else:
            action = result.get("analysis_action") or result.get("action") or result.get("state")
            if mode == "LIVE":
                text = f"Done. Live status: {action or 'updated'}."
            else:
                text = f"Done. Paper status: {action or 'updated'}."
        if model_error:
            tip = _FRIENDLY_ERRORS.get(str(model_error))
            if tip:
                text = f"{tip}\n{text}"
        return text

    def _body(
        self,
        reply: str,
        *,
        tool_calls: list[dict[str, Any]],
        error: str | None,
        openai_called: bool,
        preferred_mode: str = "PAPER",
    ) -> dict[str, Any]:
        mode = "LIVE" if str(preferred_mode or "").upper() == "LIVE" else "PAPER"
        live_tool_names = {
            "propose_live_trade",
            "approve_live_trade",
            "reject_live_trade",
            "propose_live_close",
            "propose_live_cancel_orders",
            "list_live_positions",
            "start_futures_intake",
            "continue_futures_intake",
            "live_readiness",
        }
        used_live = any(
            isinstance(c, dict) and str(c.get("name") or "") in live_tool_names for c in tool_calls
        )
        # Live intake/propose tools mean this turn is on the MAINNET Approve path,
        # even if the composer was still on PAPER when the user said "place order".
        effective_mode = "LIVE" if used_live else mode
        exchange_sent = False
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            result = call.get("result")
            if isinstance(result, dict) and result.get("exchange_order_sent") is True:
                exchange_sent = True
                break
        return {
            "reply": reply,
            "tool_calls": tool_calls,
            "openai_called": bool(openai_called),
            "llm_changed_decision": False,
            "execution_allowed": False,
            "live_orders": bool(used_live),
            "exchange_order_sent": exchange_sent,
            "execution_mode": effective_mode,
            "preferred_mode": effective_mode,
            "live_env_armed": _live_env_armed(),
            "error": error,
        }
