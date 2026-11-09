"""Thin agent registry for Orchestrator chat and shared analysis.

Wraps existing multi-agent modules. Does not place exchange orders.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig
from agent.multi_agent.pipeline import SignalPipeline
from agent.supervisor.feasibility import evaluate_hype_feasibility


CandleFetcher = Callable[..., list[Candle]]


@dataclass(frozen=True)
class AgentDescriptor:
    agent_id: str
    label: str
    role: str
    places_orders: bool = False


REGISTRY: tuple[AgentDescriptor, ...] = (
    AgentDescriptor("market", "Market Data", "Public candles, freshness, last price"),
    AgentDescriptor("trend", "Technical Trend", "EMA / trend bias"),
    AgentDescriptor("momentum", "Technical Momentum", "RSI / momentum bias"),
    AgentDescriptor("volume", "Volume", "Relative volume and price/volume agreement"),
    AgentDescriptor("structure", "Market Structure", "Swing HH/HL vs LH/LL and range breaks"),
    AgentDescriptor("regime", "Regime", "Trend/range/volatility confirmation gate"),
    AgentDescriptor("strategy", "Strategy Coordinator", "Deterministic proposal"),
    AgentDescriptor("news", "News Advisory", "Advisory context only"),
    AgentDescriptor("portfolio", "Portfolio", "Paper equity / exposure reads"),
    AgentDescriptor("risk", "Risk Engine", "Independent veto authority"),
    AgentDescriptor("execution", "Execution Gateway", "PAPER broker or gated TESTNET/LIVE deny"),
    AgentDescriptor("performance", "Performance", "Paper journal / PnL reads"),
    AgentDescriptor("reliability", "Reliability", "Supervisor heartbeat / halt"),
)


def news_advisory_enabled_from_env() -> bool:
    raw = os.getenv("NEWS_AGENT_ADVISORY_ENABLED", "false")
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def normalize_symbol(symbol: str) -> str:
    """Map chat nicknames like HYPE → HYPEUSDT."""
    raw = str(symbol or "").strip().upper().replace("/", "").replace("-", "")
    aliases = {
        "HYPE": "HYPEUSDT",
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "BNB": "BNBUSDT",
        "XRP": "XRPUSDT",
        "DOGE": "DOGEUSDT",
        "ADA": "ADAUSDT",
        "AVAX": "AVAXUSDT",
        "LINK": "LINKUSDT",
    }
    if raw in aliases:
        return aliases[raw]
    if raw and not raw.endswith("USDT") and raw.isalpha() and len(raw) <= 10:
        return f"{raw}USDT"
    return raw


PRIMARY_QUOTE_SYMBOLS: tuple[str, ...] = (
    "HYPEUSDT",
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
)


def list_available_quotes() -> dict[str, Any]:
    """Symbols Market Data Agent can quote (public Bybit USDT perpetual)."""
    lines = [
        "Market Data Agent — available public quotes (USDT perpetual / linear).",
        "Primary: " + ", ".join(PRIMARY_QUOTE_SYMBOLS) + ".",
        "Also: ask for any SYMBOLUSDT linear ticker Bybit publishes (e.g. BNBUSDT).",
        "Paper strategy research focus remains HYPEUSDT for autonomous sessions.",
        "Quote only — this list does not place an order.",
    ]
    return {
        "agent": "market",
        "symbols": list(PRIMARY_QUOTE_SYMBOLS),
        "category_default": "linear",
        "analysis_focus_symbol": "HYPEUSDT",
        "execution_allowed": False,
        "live_orders": False,
        "exchange_order_sent": False,
        "summary": "\n".join(lines),
    }


def list_agents() -> list[dict[str, Any]]:
    return [
        {
            "agent_id": item.agent_id,
            "label": item.label,
            "role": item.role,
            "places_orders": item.places_orders,
            "registered": True,
            "enabled": True,
        }
        for item in REGISTRY
    ]


def agent_status(
    *,
    paper_supervisor_enabled: bool = False,
    supervisor_state: str | None = None,
    latest_decision: dict[str, Any] | None = None,
    heartbeat_ms: int = 0,
) -> dict[str, Any]:
    from agent.supervisor.autonomy_contract import per_agent_runtime_status

    runtime = per_agent_runtime_status(
        latest_decision=latest_decision,
        supervisor_state=supervisor_state or "UNKNOWN",
        paper_supervisor_enabled=bool(paper_supervisor_enabled),
        heartbeat_ms=heartbeat_ms,
    )
    agents = runtime["agents"]
    body = {
        **runtime,
        "summary": (
            f"{len(agents)} agents registered on the SignalPipeline spine.\n"
            f"Paper supervisor: {'on' if paper_supervisor_enabled else 'off'}"
            f"{f' ({supervisor_state})' if supervisor_state else ''}.\n"
            "Mode: PAPER. Live Bybit orders stay locked.\n"
            "Per-agent status uses latest decision contributions when available "
            "(not a cloned supervisor heartbeat).\n"
            "Agents: "
            + ", ".join(item.label for item in REGISTRY)
            + ".\n"
            "For quotes: ask price of a symbol or available quotes. "
            "For entry / TP / SL / timing: ask full analysis or run all agents on a symbol."
        ),
    }
    return body


def evaluate_decision(
    *,
    symbol: str,
    category: str,
    interval: str,
    candles: list[Candle],
    now_ms: int | None = None,
    data_path: str = "orchestrator_registry",
    news_advisory_enabled: bool | None = None,
    pipeline: SignalPipeline | None = None,
) -> Any:
    """Shared decision helper for chat analyze and paper supervisor."""
    enabled = news_advisory_enabled_from_env() if news_advisory_enabled is None else bool(news_advisory_enabled)
    pipe = pipeline or SignalPipeline(config=SignalPipelineConfig(), persist=False)
    return pipe.evaluate(
        symbol=symbol.upper(),
        category=category,
        interval=interval,
        candles=candles,
        now_ms=int(now_ms or time.time() * 1000),
        data_path=data_path,
        news_advisory_enabled=enabled,
    )


def run_full_analysis(
    *,
    symbol: str,
    category: str = "linear",
    interval: str = "15",
    candles: list[Candle],
    now_ms: int | None = None,
    data_path: str = "orchestrator_full_analysis",
    include_feasibility: bool = True,
    capital_usdt: str = "5",
    risk_fraction: str = "0.01",
) -> dict[str, Any]:
    """Market → Technical → Strategy → News → Risk → optional HYPE feasibility."""
    sym = symbol.upper()
    ts = int(now_ms or time.time() * 1000)
    news_on = news_advisory_enabled_from_env()
    decision = evaluate_decision(
        symbol=sym,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=ts,
        data_path=data_path,
        news_advisory_enabled=news_on,
    )
    public = decision.to_public_dict() if hasattr(decision, "to_public_dict") else {}
    action = str(public.get("action") or getattr(getattr(decision, "action", None), "value", None) or "HOLD")
    market = public.get("market") if isinstance(public.get("market"), dict) else {}
    risk = public.get("risk") if isinstance(public.get("risk"), dict) else {}
    levels = public.get("levels") if isinstance(public.get("levels"), dict) else {}
    price = market.get("last_price")
    contributions = public.get("contributions") if isinstance(public.get("contributions"), list) else []
    agents_ran = [str(item.get("agent_id") or "") for item in contributions if isinstance(item, dict)]
    if not agents_ran:
        agents_ran = ["market", "trend", "momentum", "strategy", "risk"]
    if news_on and "news" not in agents_ran:
        agents_ran.append("news")

    feasibility: dict[str, Any] | None = None
    if include_feasibility and sym == "HYPEUSDT" and price is not None:
        try:
            feasibility = evaluate_hype_feasibility(
                price=Decimal(str(price)),
                capital=capital_usdt,
                risk_fraction=risk_fraction,
            )
        except Exception:  # noqa: BLE001
            feasibility = {"feasible": False, "reason_code": "FEASIBILITY_ERROR", "live_orders": False}

    final_action = action
    if feasibility and not feasibility.get("feasible") and action == "BUY":
        final_action = "BLOCKED"
        if isinstance(feasibility.get("reason_code"), str):
            # Keep risk veto semantics visible without raising leverage.
            pass

    entry = levels.get("entry") if isinstance(levels, dict) else None
    stop_loss = levels.get("stop_loss") if isinstance(levels, dict) else None
    take_profit = levels.get("take_profit") if isinstance(levels, dict) else None
    # Advisory fallback so chat always shows a concrete plan when directional.
    if entry is None and price is not None and final_action in {"BUY", "SELL"}:
        px = float(price)
        stop_pct = float(risk.get("stop_distance_pct") or 0.01)
        reward_pct = float(risk.get("reward_distance_pct") or (stop_pct * 2.0))
        if final_action == "BUY":
            entry, stop_loss, take_profit = px, px * (1 - stop_pct), px * (1 + reward_pct)
        else:
            entry, stop_loss, take_profit = px, px * (1 + stop_pct), px * (1 - reward_pct)
        levels = {
            **(levels if isinstance(levels, dict) else {}),
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "note": "Advisory levels derived for chat trade plan",
        }
    timing = (
        f"Timing: use confirmed {interval}m candle closes on {category} {sym}. "
        f"Evaluate after each closed {interval}m bar (not mid-candle noise). "
        f"Analysis time_ms: {ts}."
    )
    if final_action in {"HOLD", "BLOCKED"} or entry is None:
        level_lines = [
            "Side: " + final_action + ".",
            "Entry: not armed.",
            "Stop Loss (SL): not armed.",
            "Take Profit (TP): not armed.",
        ]
    else:
        level_lines = [
            f"Side: {final_action}.",
            f"Entry: {entry}.",
            f"Stop Loss (SL): {stop_loss}.",
            f"Take Profit (TP): {take_profit}.",
            f"Leave / exit target (TP): {take_profit}.",
        ]

    lines = [
        f"Full multi-agent analysis for {sym} {category} {interval}m.",
        timing,
        f"Last price: {price if price is not None else 'unavailable'}.",
        f"Agents: {', '.join(agents_ran)}.",
        f"Strategy / signal action: {action}.",
        f"Paper decision: {final_action}.",
        f"Risk verdict: {risk.get('verdict') or 'UNKNOWN'}.",
        *level_lines,
        f"Final status: {final_action}.",
        f"News advisory enabled: {news_on}.",
    ]
    explanation = str(public.get("explanation") or "").strip()
    if explanation:
        lines.append(explanation)
    if feasibility is not None:
        lines.append(
            f"Portfolio feasibility: {feasibility.get('reason_code') or feasibility.get('result') or 'n/a'}."
        )
    if final_action in {"BUY", "SELL"} and entry is not None:
        lines.append(
            'To place a PAPER order with these levels, say "I want trade {sym}" or "Approve paper trade" after proposing.'
            .replace("{sym}", sym)
        )
    lines.append(
        "Autonomous PAPER supervisor may act only on BUY/SELL after risk approval on the next confirmed candle. "
        "Execution stays PAPER-gated. This does not send a Bybit live or testnet order."
    )

    return {
        "symbol": sym,
        "category": category,
        "interval": interval,
        "market_timestamp_ms": ts,
        "last_price": price,
        "timing": timing,
        "entry": entry,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "side": final_action,
        "agents_ran": agents_ran,
        "agent_registry": list_agents(),
        "analysis_action": final_action,
        "signal_action": action,
        "risk_verdict": risk.get("verdict"),
        "explanation": explanation,
        "levels": levels,
        "news_advisory_enabled": news_on,
        "news_changed_decision": False,
        "llm_changed_decision": False,
        "feasibility": feasibility,
        "decision": public,
        "awaiting_human_approval": False,
        "human_approval_required": False,
        "execution_allowed": False,
        "live_orders": False,
        "exchange_order_sent": False,
        "execution_mode": "PAPER",
        "summary": "\n".join(lines),
    }
