"""Orchestrator and paper-supervisor API. Loopback only. No exchange orders."""

from __future__ import annotations

import os
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from agent.market_data import Candle
from agent.orchestrator.agent_registry import (
    PRIMARY_QUOTE_SYMBOLS,
    agent_status,
    list_available_quotes,
    normalize_symbol,
    run_full_analysis,
)
from agent.orchestrator.service import Orchestrator
from agent.orchestrator.futures_intake import continue_futures_intake, start_futures_intake
from agent.orchestrator.live_trade_proposals import (
    approve_live_trade,
    get_live_proposal,
    latest_pending_live_proposal,
    list_live_positions,
    propose_live_cancel_orders,
    propose_live_close,
    propose_live_trade,
    reject_live_trade,
)
from agent.orchestrator.trade_proposals import (
    approve_paper_trade,
    get_proposal,
    latest_pending_proposal,
    propose_paper_trade,
    reject_paper_trade,
)
from agent.supervisor.machine import PaperSupervisor
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.market_data.constants import SUPPORTED_INTERVALS
from apps.api.app.market_data.rest_client import (
    BybitPublicRestClient,
    HttpxPublicTransport,
    HttpTransport,
)
from apps.api.app.market_data.schemas import MarketCategory

router = APIRouter(prefix="/api/v1/orchestrator", tags=["orchestrator"])

_SUPERVISOR: PaperSupervisor | None = None
_ANALYSIS_TRANSPORT: HttpTransport | None = None
_CHAT_SYMBOLS = frozenset(PRIMARY_QUOTE_SYMBOLS)
_CHAT_PAPER_JOURNAL = "data/paper_supervisor/orchestrator_chat_paper.sqlite3"


def _enabled() -> bool:
    raw = os.getenv("CRYPTONOVA_PAPER_SUPERVISOR")
    if raw is not None and str(raw).strip() != "":
        return str(raw).strip().lower() in {"1", "true", "yes"}
    try:
        return bool(get_api_settings().paper_supervisor_enabled)
    except Exception:  # noqa: BLE001
        return False


def _journal() -> str:
    try:
        path = get_api_settings().paper_supervisor_journal.strip()
        if path:
            return path
    except Exception:  # noqa: BLE001
        pass
    return os.getenv(
        "CRYPTONOVA_PAPER_SUPERVISOR_JOURNAL",
        "data/paper_supervisor/supervisor.sqlite3",
    )


def reset_supervisor_for_tests() -> None:
    global _SUPERVISOR, _ANALYSIS_TRANSPORT
    _SUPERVISOR = None
    _ANALYSIS_TRANSPORT = None


def set_analysis_transport_for_tests(transport: HttpTransport | None) -> None:
    """Inject a public-market transport. Tests must not call Bybit."""
    global _ANALYSIS_TRANSPORT
    _ANALYSIS_TRANSPORT = transport


def _worker_token_for_journal(journal: str) -> str:
    """Stable per-journal token so API restarts reclaim the same lease owner."""
    import hashlib
    from pathlib import Path

    explicit = os.getenv("CRYPTONOVA_PAPER_SUPERVISOR_WORKER_TOKEN", "").strip()
    if explicit:
        return explicit
    try:
        key = str(Path(journal).resolve())
    except OSError:
        key = str(journal)
    return "api-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def get_supervisor() -> PaperSupervisor | None:
    global _SUPERVISOR
    if not _enabled():
        return None
    if _SUPERVISOR is None:
        journal = _journal()
        _SUPERVISOR = PaperSupervisor(journal, worker_token=_worker_token_for_journal(journal))
    return _SUPERVISOR


def _loopback(request: Request, settings: ApiSettings) -> None:
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1", "localhost", "testclient"}:
        raise HTTPException(status_code=403, detail="operator_local_only")
    if settings.app_env.strip().lower() in {"production", "prod"}:
        raise HTTPException(status_code=403, detail="controls_disabled_in_production_env")


def _disabled_status() -> dict[str, Any]:
    return {
        "enabled": False,
        "state": "STOPPED",
        "mode": "PAPER",
        "live_orders": False,
        "execution_allowed": False,
        "exchange_order_sent": False,
        "mainnet_locked": True,
        "testnet_orders": False,
        "openai_called": False,
        "risk_limits": {
            "risk_fraction": "0.01",
            "max_open_positions": 1,
            "leverage": "1",
            "live_locked": True,
        },
    }


def _attach_worker_fields(body: dict[str, Any]) -> dict[str, Any]:
    """Expose worker liveness for the Autonomy UI (Worker connected / offline)."""
    try:
        from apps.api.app.orchestrator.runtime import (
            maybe_start_paper_supervisor_worker,
            worker_status,
        )

        if body.get("enabled"):
            maybe_start_paper_supervisor_worker()
        ws = worker_status()
        body["worker_running"] = bool(ws.get("worker_running"))
        body["worker_polled_at_ms"] = ws.get("polled_at_ms")
    except Exception:  # noqa: BLE001 — status must still answer if worker attach fails
        body.setdefault("worker_running", False)
    return body


def _status_tool() -> dict[str, Any]:
    supervisor = get_supervisor()
    if supervisor is None:
        body = _disabled_status()
        body["worker_running"] = False
    else:
        body = supervisor.status()
        body["enabled"] = True
        body["openai_called"] = False
        body["risk_limits"] = _disabled_status()["risk_limits"]
        body = _attach_worker_fields(body)
    state = body.get("state") or "STOPPED"
    gate = "on" if body.get("enabled") else "off"
    auth = body.get("authorization") if isinstance(body.get("authorization"), dict) else {}
    symbol = auth.get("symbol") or "HYPEUSDT"
    capital = auth.get("capital_usdt") or "5"
    live_armed = False
    bybit_mainnet = False
    try:
        from apps.api.app.exchange.bybit_live_adapter import bybit_is_mainnet, live_mutate_allowed

        live_armed = bool(live_mutate_allowed())
        bybit_mainnet = bool(bybit_is_mainnet())
    except Exception:  # noqa: BLE001 — status must still answer
        live_armed = False
        bybit_mainnet = False
    body["autonomous"] = True
    body["per_trade_approval"] = False
    body["live_mutate_allowed"] = live_armed
    body["bybit_mainnet"] = bybit_mainnet
    body["live_unlocked"] = live_armed
    body["chat_execution_modes"] = ["PAPER", "LIVE"]
    state_nice = {
        "RUNNING": "running",
        "PAUSED": "paused",
        "STOPPED": "stopped",
        "HALTED": "halted",
        "ERROR": "in an error state",
        "STARTING": "starting",
        "STOPPING": "stopping",
    }.get(str(state).upper(), str(state).lower())
    live_line = (
        "Live Bybit trading is ready — I'll still ask you to Approve each order."
        if live_armed
        else "Live Bybit trading is not armed yet (turn on AGENT_ALLOW_LIVE and MAINNET_TRADING_ENABLED)."
    )
    body["summary"] = (
        f"Paper supervisor is {state_nice}"
        f"{' (feature on)' if gate == 'on' else ' (feature off)'}.\n"
        f"Watching {symbol} with about {capital} USDT paper capital.\n"
        "Say “Start autonomous paper trading” to let paper trades run without per-trade approval.\n"
        f"{live_line}"
    )
    return body


def _report_tool() -> dict[str, Any]:
    supervisor = get_supervisor()
    if supervisor is None:
        body = {
            **_disabled_status(),
            "equity_source": "paper_journal",
            "exchange_equity_included": False,
        }
        body["summary"] = (
            "No paper journal is open because the supervisor feature is off.\n"
            "Equity on this page stays empty. Exchange wallet equity is not included."
        )
        return body
    try:
        body = supervisor.report()
    except Exception as exc:  # noqa: BLE001 — ops desk must not 500 on journal faults
        body = {
            **_status_tool(),
            "available": False,
            "equity_source": "paper_journal",
            "exchange_equity_included": False,
            "positions": [],
            "recent_trades": [],
            "recent_events": [],
            "pending_orders": [],
            "report_error": type(exc).__name__,
        }
    if body.get("report_error") or body.get("available") is False:
        err = body.get("report_error") or body.get("last_error") or "journal_unavailable"
        body["summary"] = (
            f"Paper journal snapshot unavailable ({err}).\n"
            "Supervisor status is still shown. Stop and start a new session if the "
            "journal marker and session id drifted. Exchange wallet equity is not included."
        )
        return body
    body["summary"] = (
        "Paper journal snapshot.\n"
        f"Equity: {body.get('equity', '—')} {body.get('currency', 'USDT')}\n"
        f"Open positions: {body.get('open_positions', 0)}\n"
        f"Realized PnL: {body.get('realized_pnl', '0')}\n"
        f"Fees: {body.get('fees_paid', '0')}\n"
        f"Drawdown: {body.get('drawdown', '0')}\n"
        "These figures come from the paper journal. Exchange wallet equity is not included."
    )
    return body


def _command_tool(command: str, authorization: dict[str, Any] | None = None) -> dict[str, Any]:
    if not _enabled():
        body = {**_disabled_status(), "error": "supervisor_disabled", "worker_running": False}
        body["summary"] = (
            "Autonomous paper supervisor is disabled.\n"
            "Set CRYPTONOVA_PAPER_SUPERVISOR=true to authorize a PAPER session. "
            "Live and testnet stay locked."
        )
        return body
    supervisor = get_supervisor()
    assert supervisor is not None
    body = supervisor.command(command, authorization=authorization)
    body = _attach_worker_fields({**body, "enabled": True})
    state = body.get("state") or "STOPPED"
    auth = body.get("authorization") if isinstance(body.get("authorization"), dict) else {}
    symbol = auth.get("symbol") or "HYPEUSDT"
    capital = auth.get("capital_usdt") or "5"
    duration = auth.get("duration_hours") or 48
    if body.get("error") == "command_not_allowed":
        body["summary"] = f"Command '{command}' was refused. Supervisor stayed {state}."
        return body
    if body.get("error") == "session_already_active":
        body["summary"] = (
            f"A paper session is already {state}. Pause, stop, or halt before starting a new one."
        )
        return body
    if command == "start":
        body["summary"] = (
            f"Autonomous PAPER session started for {symbol}.\n"
            f"Symbol: {symbol}\n"
            f"Capital: {capital} USDT\n"
            f"Risk: 1% per trade\n"
            f"Duration: {duration} hours\n"
            "The supervisor places paper orders automatically when risk approves.\n"
            "No per-trade chat approval is required.\n"
            "Live Bybit orders stay disabled."
        )
    elif command == "pause":
        body["summary"] = (
            f"Paper supervisor paused.\n"
            f"State: {state}\n"
            "No new paper cycles run until you resume."
        )
    elif command == "resume":
        body["summary"] = (
            f"Paper supervisor resumed.\n"
            f"State: {state}\n"
            "Autonomous paper trading continues under the same session bounds."
        )
    elif command == "stop":
        body["summary"] = (
            f"Paper supervisor stopped.\n"
            f"State: {state}\n"
            "Autonomous paper trading will not place new simulated orders."
        )
    elif command == "halt":
        body["summary"] = (
            f"Emergency halt engaged.\n"
            f"State: {state}\n"
            "New paper entries are blocked. Protective exits may still process."
        )
    else:
        body["summary"] = f"Supervisor command '{command}' applied. State {state}."
    body["live_orders"] = False
    body["exchange_order_sent"] = False
    body["autonomous"] = True
    body["per_trade_approval"] = False
    return body


def _fetch_public_candles(symbol: str, category: str, interval: str) -> tuple[list[Candle], str]:
    owned = _ANALYSIS_TRANSPORT is None
    transport = _ANALYSIS_TRANSPORT if not owned else HttpxPublicTransport()
    try:
        client = BybitPublicRestClient(transport)
        cat = MarketCategory(category)
        kl = client.get_klines(category=cat, symbol=symbol, interval=interval, limit=250)
        candles = [
            Candle(
                start=int(bar.time) * 1000,
                open=float(bar.open),
                high=float(bar.high),
                low=float(bar.low),
                close=float(bar.close),
                volume=float(bar.volume),
            )
            for bar in kl.candles
        ]
        return candles, (kl.data_path or "public_rest_only")
    finally:
        if owned and hasattr(transport, "close"):
            transport.close()


def _analyze_tool(symbol: str, category: str = "linear", interval: str = "15") -> dict[str, Any]:
    return _run_full_analysis_tool(symbol, category, interval)


def _get_market_price_tool(symbol: str, category: str = "linear") -> dict[str, Any]:
    """Market Data Agent — public ticker only. Not a trade decision."""
    sym = normalize_symbol(symbol)
    cat = (category or "linear").strip().lower()
    if cat not in {"linear", "spot"}:
        cat = "linear"
    # Default USDT perps to linear (HYPE/BNB/etc.).
    if sym.endswith("USDT"):
        cat = "linear"
    owned = _ANALYSIS_TRANSPORT is None
    transport = _ANALYSIS_TRANSPORT if not owned else HttpxPublicTransport()
    try:
        client = BybitPublicRestClient(transport)
        tickers = client.get_tickers(category=MarketCategory(cat), symbols=[sym])
        if not tickers.tickers:
            raise RuntimeError("ticker_missing")
        row = tickers.tickers[0]
        last = float(row.last_price)
        mark = getattr(row, "mark_price", None)
        bid = getattr(row, "bid1", None)
        ask = getattr(row, "ask1", None)
        pct = getattr(row, "price_24h_pct", None)
        lines = [
            f"Market Data Agent — {sym} ({cat}).",
            f"Last price: {last}.",
        ]
        if mark is not None:
            lines.append(f"Mark price: {mark}.")
        if bid is not None and ask is not None:
            lines.append(f"Bid/Ask: {bid} / {ask}.")
        if pct is not None:
            lines.append(f"24h change: {pct}%.")
        lines.append("Quote only — no trade analysis and no order was sent.")
        return {
            "agent": "market",
            "symbol": sym,
            "category": cat,
            "ok": True,
            "last_price": last,
            "mark_price": mark,
            "bid1": bid,
            "ask1": ask,
            "price_24h_pct": pct,
            "analysis_action": None,
            "execution_allowed": False,
            "live_orders": False,
            "exchange_order_sent": False,
            "llm_changed_decision": False,
            "summary": "\n".join(lines),
        }
    except Exception:
        return {
            "agent": "market",
            "symbol": sym,
            "category": cat,
            "ok": False,
            "analysis_action": None,
            "execution_allowed": False,
            "live_orders": False,
            "exchange_order_sent": False,
            "summary": (
                f"Market Data Agent could not read the public {cat} ticker for {sym}.\n"
                "Try list_market_quotes for supported symbols. No order was sent."
            ),
        }
    finally:
        if owned and hasattr(transport, "close"):
            transport.close()


def _list_market_quotes_tool() -> dict[str, Any]:
    return list_available_quotes()


def _run_full_analysis_tool(symbol: str, category: str = "linear", interval: str = "15") -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    # Coerce common bad OpenAI defaults for HYPE perpetual research.
    if sym == "HYPEUSDT":
        category = "linear"
        if interval not in SUPPORTED_INTERVALS:
            interval = "15"
    blocked = {
        "symbol": sym,
        "category": category,
        "interval": interval,
        "analysis_action": "BLOCKED",
        "execution_allowed": False,
        "live_orders": False,
        "news_changed_decision": False,
        "llm_changed_decision": False,
        "exchange_order_sent": False,
    }
    # Allow primary research symbols plus any USDT linear/spot ticker Bybit serves.
    allowed_symbol = sym in _CHAT_SYMBOLS or (sym.endswith("USDT") and len(sym) >= 6)
    if not allowed_symbol or category not in {"linear", "spot"} or interval not in SUPPORTED_INTERVALS:
        blocked["summary"] = (
            f"{sym} {category} {interval} is outside the paper research list.\n"
            "Ask list_market_quotes for primary symbols. Paper decision: BLOCKED. No order was sent."
        )
        return blocked
    try:
        candles, data_path = _fetch_public_candles(sym, category, interval)
        body = run_full_analysis(
            symbol=sym,
            category=category,
            interval=interval,
            candles=candles,
            now_ms=int(time.time() * 1000),
            data_path=data_path,
        )
    except Exception:
        blocked["reason"] = "market_data_unavailable"
        blocked["summary"] = (
            f"Public {category} candles for {sym} could not be read.\n"
            "Paper decision: BLOCKED. No order was sent."
        )
        return blocked
    # Keep analyze_symbol contract fields used by UI/tests.
    body["last_price"] = body.get("last_price")
    body["risk_verdict"] = body.get("risk_verdict")
    try:
        from agent.orchestrator.analysis_memory import remember_analysis

        remember_analysis(body)
    except Exception:  # noqa: BLE001
        pass
    summary = str(body.get("summary") or "").strip()
    action = str(body.get("analysis_action") or body.get("action") or "HOLD").upper()
    if action in {"BUY", "SELL"}:
        next_steps = (
            f"\n\nNext: to place a live {sym} order on Bybit, say "
            f'“Place futures order {sym}” (or “Place the order”). '
            "I’ll reuse this side/SL/TP and ask for Market/Limit, leverage, and "
            "how many USDT to use for the trade (e.g. “use 3 USDT” — not your full balance). "
            'Example: "Market leverage 5 use 3 USDT". '
            "Then click Approve — nothing is sent to Bybit until you Approve."
        )
    else:
        next_steps = (
            f"\n\nNext: no live entry is suggested while the decision is {action}. "
            f'If you still want a manual Bybit order, say “Place futures order {sym}” '
            "and I’ll collect side, Market/Limit, qty, leverage, and SL/TP. "
            "Approve is still required before Bybit."
        )
    if "Next:" not in summary:
        body["summary"] = (summary + next_steps).strip() if summary else (
            f"Full multi-agent analysis for {sym} linear {interval}.\n"
            f"Decision: {action}.{next_steps}"
        )
    return body


def _agent_status_tool() -> dict[str, Any]:
    status: dict[str, Any]
    try:
        status = _status_tool()
    except Exception:  # noqa: BLE001
        status = _disabled_status()
    latest = status.get("latest_decision") if isinstance(status.get("latest_decision"), dict) else None
    return agent_status(
        paper_supervisor_enabled=_enabled(),
        supervisor_state=str(status.get("state") or "STOPPED"),
        latest_decision=latest,
        heartbeat_ms=int(status.get("heartbeat_ms") or 0),
    )


def _autonomy_snapshot_tool() -> dict[str, Any]:
    from agent.supervisor.autonomy_contract import build_autonomy_snapshot

    status = _status_tool()
    report = _report_tool()
    return build_autonomy_snapshot(
        status=status,
        report=report,
        paper_supervisor_enabled=_enabled(),
        decision_queue=status.get("decision_queue")
        if isinstance(status.get("decision_queue"), list)
        else [],
    )


def _decision_queue_tool() -> dict[str, Any]:
    snap = _autonomy_snapshot_tool()
    return {
        "mode": "PAPER",
        "live_orders": False,
        "decision_queue": snap.get("decision_queue") or [],
        "latest_decision": snap.get("latest_decision"),
        "strategy_version": snap.get("strategy_version"),
        "honesty_note": snap.get("honesty_note"),
    }


def _risk_feed_tool() -> dict[str, Any]:
    snap = _autonomy_snapshot_tool()
    return snap.get("risk") or {"mode": "PAPER", "live_orders": False, "halted": False}


def _openai_usage_tool() -> dict[str, Any]:
    from agent.orchestrator.openai_adapter import OrchestratorOpenAiConfig
    from agent.orchestrator.usage_ledger import UsageLedger

    config = OrchestratorOpenAiConfig.from_env()
    ledger = UsageLedger(config.ledger_path)
    body = config.public_status(ledger)
    body["summary"] = (
        f"OpenAI orchestrator enabled={body['enabled']}, spend_approved={body['spend_approved']}.\n"
        f"Gates open={body['gates_open']}. Model configured={body['model_configured']}.\n"
        f"Spent 24h ${body['spent_usd_24h']:.4f} / daily ${body['daily_budget_usd']:.2f}. "
        f"Spent 30d ${body['spent_usd_30d']:.4f} / monthly ${body['monthly_budget_usd']:.2f}.\n"
        "Paid calls stay off until both spend gates are approved. "
        "This does not authorize a live or testnet order."
    )
    body["live_orders"] = False
    body["execution_allowed"] = False
    return body


def _live_readiness_tool() -> dict[str, Any]:
    from agent.orchestrator.live_authorization import live_readiness_checklist

    return live_readiness_checklist(paper_supervisor_enabled=_enabled())


def _hype_feasibility_tool() -> dict[str, Any]:
    from decimal import Decimal

    from agent.supervisor.feasibility import evaluate_hype_feasibility

    owned = _ANALYSIS_TRANSPORT is None
    transport = _ANALYSIS_TRANSPORT if not owned else HttpxPublicTransport()
    price = Decimal("76")
    try:
        client = BybitPublicRestClient(transport)
        tickers = client.get_tickers(category=MarketCategory.linear, symbols=["HYPEUSDT"])
        if tickers.tickers:
            price = Decimal(str(tickers.tickers[0].last_price))
    except Exception:  # noqa: BLE001 — feasibility still answers with last known style price
        pass
    finally:
        if owned and hasattr(transport, "close"):
            transport.close()
    return evaluate_hype_feasibility(price=price)


def _symbol_allowed(sym: str, category: str, interval: str) -> bool:
    allowed_symbol = sym in _CHAT_SYMBOLS or (sym.endswith("USDT") and len(sym) >= 6)
    return bool(allowed_symbol and category in {"linear", "spot"} and interval in SUPPORTED_INTERVALS)


def _propose_paper_trade_tool(symbol: str, category: str = "linear", interval: str = "15") -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    if sym == "HYPEUSDT":
        category = "linear"
        if interval not in SUPPORTED_INTERVALS:
            interval = "15"
    blocked = {
        "symbol": sym,
        "category": category,
        "interval": interval,
        "analysis_action": "BLOCKED",
        "awaiting_human_approval": False,
        "execution_allowed": False,
        "live_orders": False,
        "exchange_order_sent": False,
        "summary": (
            f"{sym} {category} {interval} cannot be proposed.\n"
            "Ask list_market_quotes for supported symbols. No order was sent."
        ),
    }
    if not _symbol_allowed(sym, category, interval):
        return blocked
    try:
        candles, _data_path = _fetch_public_candles(sym, category, interval)
        return propose_paper_trade(
            symbol=sym,
            category=category,
            interval=interval,
            candles=candles,
            now_ms=int(time.time() * 1000),
        )
    except Exception:
        blocked["summary"] = (
            f"Public candles for {sym} unavailable.\n"
            "Trade plan not created. No order was sent."
        )
        return blocked


def _approve_paper_trade_tool(proposal_id: str = "") -> dict[str, Any]:
    try:
        proposal = get_proposal(proposal_id) if str(proposal_id or "").strip() else None
        if proposal is None:
            proposal = latest_pending_proposal()
        if proposal is None:
            return approve_paper_trade(None, candles=None, journal_path=_CHAT_PAPER_JOURNAL)
        candles, _ = _fetch_public_candles(proposal.symbol, proposal.category, proposal.interval)
        return approve_paper_trade(
            proposal.proposal_id,
            candles=candles,
            journal_path=_CHAT_PAPER_JOURNAL,
        )
    except Exception:
        return {
            "ok": False,
            "summary": "Paper approve failed (market data or journal). No Bybit order was sent.",
            "live_orders": False,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }


def _reject_paper_trade_tool(proposal_id: str = "") -> dict[str, Any]:
    return reject_paper_trade(proposal_id or "")


def _propose_live_trade_tool(symbol: str, category: str = "linear", interval: str = "15") -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    if sym == "HYPEUSDT":
        category = "linear"
        if interval not in SUPPORTED_INTERVALS:
            interval = "15"
    blocked = {
        "symbol": sym,
        "category": category,
        "interval": interval,
        "analysis_action": "BLOCKED",
        "awaiting_human_approval": False,
        "execution_allowed": False,
        "live_orders": True,
        "exchange_order_sent": False,
        "summary": (
            f"{sym} {category} {interval} cannot be proposed for LIVE.\n"
            "Ask list_market_quotes for supported symbols. No order was sent."
        ),
    }
    if not _symbol_allowed(sym, category, interval):
        return blocked
    try:
        candles, _data_path = _fetch_public_candles(sym, category, interval)
        return propose_live_trade(
            symbol=sym,
            category=category,
            interval=interval,
            candles=candles,
            now_ms=int(time.time() * 1000),
        )
    except Exception:
        blocked["summary"] = (
            f"Public candles for {sym} unavailable.\n"
            "LIVE trade plan not created. No order was sent."
        )
        return blocked


def _approve_live_trade_tool(proposal_id: str = "") -> dict[str, Any]:
    try:
        proposal = get_live_proposal(proposal_id) if str(proposal_id or "").strip() else None
        if proposal is None:
            proposal = latest_pending_live_proposal()
        if proposal is None:
            return approve_live_trade(None, candles=None)
        candles, _ = _fetch_public_candles(proposal.symbol, proposal.category, proposal.interval)
        return approve_live_trade(proposal.proposal_id, candles=candles)
    except Exception:
        return {
            "ok": False,
            "summary": "LIVE approve failed (market data or Bybit). No confirmed exchange order.",
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
        }


def _reject_live_trade_tool(proposal_id: str = "") -> dict[str, Any]:
    return reject_live_trade(proposal_id or "")


def _propose_live_close_tool(symbol: str, category: str = "linear") -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    if sym == "HYPEUSDT":
        category = "linear"
    return propose_live_close(symbol=sym, category=category)


def _propose_live_cancel_orders_tool(symbol: str, category: str = "linear") -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    if sym == "HYPEUSDT":
        category = "linear"
    return propose_live_cancel_orders(symbol=sym, category=category)


def _list_live_positions_tool(symbol: str = "HYPEUSDT", category: str = "linear") -> dict[str, Any]:
    sym = normalize_symbol(symbol)
    if sym == "HYPEUSDT":
        category = "linear"
    return list_live_positions(symbol=sym, category=category)


def _orchestrator() -> Orchestrator:
    return Orchestrator(
        {
            "supervisor_status": lambda: _status_tool(),
            "paper_report": lambda: _report_tool(),
            "supervisor_command": lambda command: _command_tool(command),
            "analyze_symbol": lambda symbol, category="linear", interval="15": _analyze_tool(
                symbol, category, interval
            ),
            "run_full_analysis": lambda symbol, category="linear", interval="15": _run_full_analysis_tool(
                symbol, category, interval
            ),
            "propose_paper_trade": lambda symbol, category="linear", interval="15": _propose_paper_trade_tool(
                symbol, category, interval
            ),
            "approve_paper_trade": lambda proposal_id="": _approve_paper_trade_tool(proposal_id),
            "reject_paper_trade": lambda proposal_id="": _reject_paper_trade_tool(proposal_id),
            "propose_live_trade": lambda symbol, category="linear", interval="15": _propose_live_trade_tool(
                symbol, category, interval
            ),
            "approve_live_trade": lambda proposal_id="": _approve_live_trade_tool(proposal_id),
            "reject_live_trade": lambda proposal_id="": _reject_live_trade_tool(proposal_id),
            "propose_live_close": lambda symbol, category="linear": _propose_live_close_tool(
                symbol, category
            ),
            "propose_live_cancel_orders": lambda symbol, category="linear": _propose_live_cancel_orders_tool(
                symbol, category
            ),
            "list_live_positions": lambda symbol="HYPEUSDT", category="linear": _list_live_positions_tool(
                symbol, category
            ),
            "start_futures_intake": lambda symbol="HYPEUSDT", category="linear", message="": start_futures_intake(
                symbol=symbol, category=category, message=message
            ),
            "continue_futures_intake": lambda message="": continue_futures_intake(message),
            "agent_status": lambda: _agent_status_tool(),
            "get_market_price": lambda symbol, category="linear": _get_market_price_tool(
                symbol, category
            ),
            "list_market_quotes": lambda: _list_market_quotes_tool(),
            "openai_usage": lambda: _openai_usage_tool(),
            "live_readiness": lambda: _live_readiness_tool(),
            "hype_feasibility": lambda: _hype_feasibility_tool(),
        }
    )


@router.get("/status")
def orchestrator_status(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _loopback(request, settings)
    return _status_tool()


@router.post("/command")
def orchestrator_command(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    body: dict[str, Any],
) -> dict[str, Any]:
    """Operator session controls from Autonomy UI. Paper only — never live."""
    _loopback(request, settings)
    command = str(body.get("command") or "").strip().lower()
    authorization = body.get("authorization") if isinstance(body.get("authorization"), dict) else None
    allowed = {"start", "pause", "resume", "stop", "halt"}
    if command not in allowed:
        raise HTTPException(status_code=400, detail="command_not_allowed")
    result = _command_tool(command, authorization=authorization)
    if result.get("error") == "supervisor_disabled":
        raise HTTPException(status_code=503, detail="supervisor_disabled")
    if result.get("error") == "command_not_allowed":
        raise HTTPException(status_code=409, detail="command_not_allowed")
    return result


@router.post("/chat")
def orchestrator_chat(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
    body: dict[str, Any],
) -> dict[str, Any]:
    _loopback(request, settings)
    message = str(body.get("message") or "")
    raw_mode = str(
        body.get("execution_mode")
        or body.get("preferred_mode")
        or body.get("mode")
        or "PAPER"
    ).strip().upper()
    preferred_mode = "LIVE" if raw_mode == "LIVE" else "PAPER"
    return _orchestrator().handle(
        message,
        cancelled=bool(body.get("cancelled")),
        preferred_mode=preferred_mode,
    )


@router.get("/report")
def orchestrator_report(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _loopback(request, settings)
    return _report_tool()


@router.get("/autonomy")
def orchestrator_autonomy(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    """Unified PAPER autonomy contract for the ops desk."""
    _loopback(request, settings)
    return _autonomy_snapshot_tool()


@router.get("/decisions")
def orchestrator_decisions(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _loopback(request, settings)
    return _decision_queue_tool()


@router.get("/agents/runtime")
def orchestrator_agents_runtime(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _loopback(request, settings)
    return _agent_status_tool()


@router.get("/risk")
def orchestrator_risk(
    request: Request,
    settings: Annotated[ApiSettings, Depends(get_api_settings)],
) -> dict[str, Any]:
    _loopback(request, settings)
    return _risk_feed_tool()
