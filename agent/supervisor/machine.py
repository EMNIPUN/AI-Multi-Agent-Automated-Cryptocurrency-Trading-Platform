"""Paper supervisor state machine over the isolated SQLite paper journal."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from agent.market_data import Candle
from agent.multi_agent.types import DecisionAction
from agent.paper.auto_trade import AutomaticPaperTrader
from agent.paper.config import PaperBrokerConfig
from agent.supervisor.session import (
    PaperSessionAuthorization,
    authorization_from_dict,
)
from agent.supervisor.locking import supervisor_lock


class SupervisorState(str, Enum):
    STOPPED = "STOPPED"
    STARTING = "STARTING"
    RECONCILING = "RECONCILING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    HALTED = "HALTED"
    STOPPING = "STOPPING"
    ERROR = "ERROR"
    RECOVERING = "RECOVERING"


_LEASE_MS = 30_000


def _refuse_remote_journal(journal_path: str | Path) -> None:
    text = str(journal_path).strip().lower()
    if "://" in text or text.startswith("postgres"):
        raise RuntimeError("supervisor_postgres_runtime_not_enabled")


class PaperSupervisor:
    def __init__(
        self,
        journal_path: str | Path,
        config: PaperBrokerConfig | None = None,
        *,
        evaluate: Callable[..., Any] | None = None,
        worker_token: str | None = None,
    ) -> None:
        _refuse_remote_journal(journal_path)
        self.journal_path = Path(journal_path)
        self.config = config
        self.worker_token = worker_token or uuid.uuid4().hex
        self._evaluate = evaluate
        self._trader: AutomaticPaperTrader | None = None
        self.state_path = Path(str(self.journal_path) + ".supervisor.json")
        self._authorization: PaperSessionAuthorization | None = None
        self._pipeline = None

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"state": SupervisorState.STOPPED.value, "owner": None, "heartbeat_ms": 0}
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("state") not in {state.value for state in SupervisorState}:
                raise ValueError("invalid state")
            return data
        except (ValueError, OSError):
            return {"state": "ERROR", "last_error": "supervisor_state_corrupt", "block_new_exposure": True}

    def _save(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_name(self.state_path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
            os.replace(temporary, self.state_path)
        finally:
            temporary.unlink(missing_ok=True)

    def _trader_open(self) -> AutomaticPaperTrader:
        if self._trader is None:
            data = self._load()
            expected_session = data.get("session_id")
            marker = self.journal_path.with_suffix(self.journal_path.suffix + ".session")
            marker_session = (
                marker.read_text(encoding="utf-8").strip()
                if marker.exists()
                else ""
            )
            if expected_session and (
                not self.journal_path.exists()
                or not marker_session
                or marker_session != expected_session
            ):
                # Journal marker is durable truth. Heal drifted supervisor.json session_id
                # when the marked session is still ACTIVE; never create a new session here.
                healed = False
                if self.journal_path.exists() and marker_session:
                    try:
                        from agent.paper.models import SessionStatus
                        from agent.paper.store import PaperStore

                        store = PaperStore(self.journal_path, isolated_sqlite=True)
                        existing = store.get_session(marker_session)
                        if existing is not None and existing.status is SessionStatus.ACTIVE:
                            data["session_id"] = marker_session
                            data["last_error"] = "journal_session_healed"
                            self._save(data)
                            expected_session = marker_session
                            healed = True
                    except Exception:  # noqa: BLE001
                        healed = False
                if not healed:
                    raise RuntimeError("journal_session_mismatch")
            config = self.config
            auth = self._current_authorization()
            if config is None and auth is not None:
                capital = auth.capital_usdt
                config = PaperBrokerConfig(
                    initial_balance=capital,
                    max_total_exposure=capital,
                )
            self._trader = AutomaticPaperTrader(
                self.journal_path, config, risk_fraction=auth.risk_fraction if auth else None,
            )
            if expected_session and self._trader.session.session_id != expected_session:
                self._trader = None
                raise RuntimeError("journal_session_mismatch")
        return self._trader

    def _current_authorization(self) -> PaperSessionAuthorization | None:
        if self._authorization is not None:
            return self._authorization
        raw = self._load().get("authorization")
        if isinstance(raw, dict):
            self._authorization = authorization_from_dict(raw)
            return self._authorization
        return None

    def _claim(self, now_ms: int) -> None:
        data = self._load()
        owner = data.get("owner")
        heartbeat = int(data.get("heartbeat_ms") or 0)
        if owner and owner != self.worker_token and now_ms - heartbeat < _LEASE_MS:
            raise RuntimeError("supervisor_worker_busy")
        data["owner"] = self.worker_token
        data["heartbeat_ms"] = now_ms
        self._save(data)

    def adopt_lease(self, *, now_ms: int | None = None) -> dict[str, Any]:
        """Force-take the worker lease for this process.

        Used by the local API paper worker on start/restart so a fresh process is
        not blocked for _LEASE_MS by a dead owner's heartbeat. Distinct worker
        tokens still refuse each other via _claim during normal commands/cycles.
        """
        now = int(now_ms or time.time() * 1000)
        with supervisor_lock(Path(str(self.state_path) + ".lock")):
            data = self._load()
            previous = data.get("owner")
            data["owner"] = self.worker_token
            data["heartbeat_ms"] = now
            self._save(data)
            return {
                "adopted": True,
                "previous_owner": previous,
                "owner": self.worker_token,
                "heartbeat_ms": now,
            }

    def command(
        self,
        name: str,
        *,
        now_ms: int = 0,
        authorization: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with supervisor_lock(Path(str(self.state_path) + ".lock")):
            return self._command(name, now_ms=now_ms, authorization=authorization)

    def _command(self, name: str, *, now_ms: int, authorization: dict[str, Any] | None) -> dict[str, Any]:
        command = (name or "").strip().lower()
        now_ms = int(now_ms or time.time() * 1000)
        data = self._load()
        state = SupervisorState(data.get("state") or SupervisorState.STOPPED.value)
        if data.get("last_error") == "supervisor_state_corrupt":
            return self.status(error="supervisor_state_corrupt")
        if command == "start":
            self._claim(now_ms)
            if state in {SupervisorState.RUNNING, SupervisorState.PAUSED, SupervisorState.HALTED, SupervisorState.STOPPING}:
                return self.status(error="session_already_active")
            auth = authorization_from_dict(authorization, now_ms=now_ms)
            if self.config is None:
                self.config = PaperBrokerConfig(
                    initial_balance=auth.capital_usdt,
                    max_total_exposure=auth.capital_usdt,
                )
            elif not authorization or "capital_usdt" not in authorization:
                # Keep an explicit broker config as the capital source for tests / local runs.
                auth = authorization_from_dict(
                    {
                        **auth.to_dict(),
                        "capital_usdt": str(self.config.initial_balance),
                    },
                    now_ms=now_ms,
                )
            self._authorization = auth
            self._trader = None
            data = self._load()
            previous_auth = data.get("authorization") or {}
            if data.get("session_id") and any(
                str(previous_auth.get(key)) != str(auth.to_dict().get(key))
                for key in ("symbol", "category", "interval", "capital_usdt", "risk_fraction")
            ):
                self._authorization = authorization_from_dict(previous_auth)
                return self.status(error="authorization_change_requires_new_journal")
            data["state"] = SupervisorState.STARTING.value
            data["authorization"] = auth.to_dict()
            data["autonomous"] = True
            data["per_trade_approval"] = False
            self._save(data)
            data["state"] = SupervisorState.RECONCILING.value
            self._save(data)
            try:
                session = self._trader_open().session
            except Exception as exc:  # noqa: BLE001
                data["state"] = SupervisorState.ERROR.value
                data["last_error"] = "journal_unavailable"
                data["block_new_exposure"] = True
                self._save(data)
                return self.status(error=type(exc).__name__)
            if session is None or str(getattr(session.status, "value", session.status)) != "ACTIVE":
                data["state"] = SupervisorState.ERROR.value
                data["last_error"] = "unknown_position_state"
                data["block_new_exposure"] = True
                self._save(data)
                return self.status()
            data["state"] = SupervisorState.RUNNING.value
            data["last_error"] = None
            data["block_new_exposure"] = False
            data["session_id"] = session.session_id
            data["authorization"] = auth.to_dict()
            self._save(data)
            return self.status()
        if command not in {"pause", "resume", "stop", "halt"}:
            return self.status(error="command_not_allowed")
        self._claim(now_ms)
        data = self._load()
        if command == "pause" and state is SupervisorState.RUNNING:
            data["state"] = SupervisorState.PAUSED.value
            data["block_new_exposure"] = True
        elif command == "resume" and state is SupervisorState.PAUSED:
            auth = self._current_authorization()
            if auth and auth.expired(now_ms):
                return self.status(error="session_expired")
            data["state"] = SupervisorState.RUNNING.value
            data["block_new_exposure"] = False
        elif command == "stop":
            data["state"] = SupervisorState.STOPPING.value
            data["block_new_exposure"] = True
        elif command == "halt":
            data["state"] = SupervisorState.HALTED.value
            data["block_new_exposure"] = True
        else:
            return self.status(error="command_not_allowed")
        if command in {"pause", "stop", "halt"} and data.get("session_id"):
            try:
                trader = self._trader_open()
                trader.block_pending_entries(reason=f"SUPERVISOR_{data['state']}", now_ms=now_ms)
                if command == "stop":
                    positions = trader.store.get_open_positions(trader.session.session_id)
                    if not positions:
                        data["state"] = SupervisorState.STOPPED.value
                        data["owner"] = None
                    elif data.get("last_candle_start") is not None:
                        from agent.paper.models import PaperCandle

                        auth = self._current_authorization()
                        for position in positions:
                            price = position.mark_price
                            if price is not None:
                                trader.request_close(PaperCandle(
                                    start_ms=int(data["last_candle_start"]), open=price, high=price, low=price,
                                    close=price, symbol=position.symbol, interval=auth.interval if auth else "15",
                                ), now_ms=now_ms)
            except Exception as exc:
                # Journal drift must not trap the operator — allow force stop.
                if command == "stop":
                    data["state"] = SupervisorState.STOPPED.value
                    data["owner"] = None
                    data["session_id"] = None
                    data["block_new_exposure"] = True
                    data["last_error"] = f"force_stopped:{type(exc).__name__}"
                    self._trader = None
                else:
                    data["state"] = SupervisorState.ERROR.value
                    data["last_error"] = "journal_write_failed"
        elif command == "stop":
            data["state"] = SupervisorState.STOPPED.value
            data["owner"] = None
        data["heartbeat_ms"] = now_ms
        self._save(data)
        return self.status()

    def run_cycle(
        self,
        candles: list[Candle],
        *,
        symbol: str,
        category: str,
        interval: str,
        now_ms: int,
        data_fresh: bool = True,
    ) -> dict[str, Any]:
        with supervisor_lock(Path(str(self.state_path) + ".lock")):
            return self._run_cycle(candles, symbol=symbol, category=category, interval=interval, now_ms=now_ms, data_fresh=data_fresh)

    def _run_cycle(self, candles: list[Candle], *, symbol: str, category: str, interval: str, now_ms: int, data_fresh: bool) -> dict[str, Any]:
        data = self._load()
        state = SupervisorState(data.get("state") or SupervisorState.STOPPED.value)
        if state is SupervisorState.ERROR and data.get("last_error") == "market_data_unavailable":
            state = SupervisorState(data.get("recovery_state") or SupervisorState.RUNNING.value)
        if state not in {SupervisorState.RUNNING, SupervisorState.PAUSED, SupervisorState.HALTED, SupervisorState.STOPPING}:
            return self.status(skipped=True, reason="supervisor_not_running")
        self._claim(now_ms)
        data = self._load()
        auth = self._current_authorization()
        if auth is None or (symbol.upper(), category.lower(), str(interval)) != (auth.symbol, auth.category, auth.interval):
            return self.status(skipped=True, reason="authorization_scope_mismatch", block_new_exposure=True)
        if auth is not None and auth.expired(now_ms):
            state = SupervisorState.STOPPING
            data["state"] = state.value
            data["last_error"] = "session_expired"
            data["block_new_exposure"] = True
        if not candles or not data_fresh:
            data["recovery_state"] = state.value
            data["state"] = SupervisorState.ERROR.value
            data["last_error"] = "market_data_unavailable"
            data["block_new_exposure"] = True
            self._save(data)
            return self.status(reason="market_data_unavailable")
        data["state"] = state.value
        if data.get("last_error") == "market_data_unavailable":
            data["last_error"] = None
            data["block_new_exposure"] = state is not SupervisorState.RUNNING
        candle_start = int(candles[-1].start)
        previous_candle = data.get("last_candle_start")
        if previous_candle is not None and candle_start <= int(previous_candle):
            self._save(data)
            return self.status(skipped=True, reason="duplicate_candle" if candle_start == int(previous_candle) else "out_of_order_candle")
        try:
            trader = self._trader_open()
            positions_known = trader.store.get_open_positions(trader.session.session_id)
        except Exception:  # noqa: BLE001
            data["state"] = SupervisorState.ERROR.value
            data["last_error"] = "unknown_position_state"
            data["block_new_exposure"] = True
            self._save(data)
            return self.status(reason="unknown_position_state")
        from agent.backtest.execution_adapter import market_to_paper_candle

        paper_candle = market_to_paper_candle(candles[-1], symbol=symbol, interval=interval)
        if not paper_candle.valid() or any(candles[index].start >= candles[index + 1].start for index in range(len(candles) - 1)):
            data.update(state="ERROR", last_error="market_data_unavailable", recovery_state=state.value, block_new_exposure=True)
            self._save(data)
            return self.status(reason="invalid_candles")
        decision = None
        action = "HOLD"
        try:
            if state is not SupervisorState.RUNNING:
                trader.block_pending_entries(reason=f"SUPERVISOR_{state.value}", now_ms=now_ms)
            # Replay missed bars chronologically for pending fills and protective exits;
            # historical bars never generate fresh entry decisions.
            unseen = [bar for bar in candles if previous_candle is not None and int(bar.start) > int(previous_candle)] or [candles[-1]]
            fills = []
            for bar in unseen:
                fills.extend(trader._advance(market_to_paper_candle(bar, symbol=symbol, interval=interval), interval=interval))
            halt_reason = self._risk_halt(trader, data, now_ms=now_ms)
            if halt_reason and state is SupervisorState.RUNNING:
                state = SupervisorState.HALTED
                data.update(state=state.value, last_error=halt_reason, block_new_exposure=True)
                trader.block_pending_entries(reason=halt_reason, now_ms=now_ms)
            if state is SupervisorState.STOPPING:
                closes = trader.request_close(paper_candle, now_ms=now_ms)
                reason = "session_expired" if auth and auth.expired(now_ms) else "STOPPING_CLOSE_REQUESTED"
                result = trader.snapshot(action="SELL", submit=closes[0] if closes else None, fills=fills, reason=reason)
                if result["open_positions"] == 0:
                    data["state"] = SupervisorState.STOPPED.value
                    data["owner"] = None
            elif state in {SupervisorState.PAUSED, SupervisorState.HALTED}:
                reason = "HALTED_BLOCKED_ENTRY" if state is SupervisorState.HALTED else "PAUSED_PROTECTIVE_MONITORING"
                result = trader.snapshot(action="HOLD", submit=None, fills=fills, reason=reason)
            else:
                decision = self._decision(candles, symbol=symbol, category=category, interval=interval, now_ms=now_ms)
                action = decision.action.value if hasattr(decision.action, "value") else str(decision.action)
                if action == DecisionAction.BUY.value and not self._budget_allows_entry(candles[-1].close, auth):
                    result = trader.snapshot(action="HOLD", submit=None, fills=fills, reason="FLAT_BUDGET")
                    action = "HOLD"
                else:
                    if (str(decision.symbol).upper(), str(decision.category).lower(), str(decision.interval)) != (auth.symbol, auth.category, auth.interval):
                        result = trader.snapshot(action="HOLD", submit=None, fills=fills, reason="DECISION_SCOPE_MISMATCH")
                        action = "HOLD"
                    else:
                        result = trader.apply_decision(decision, paper_candle)
                        result["fill_reasons"] = [fill.reason for fill in fills]
                data["latest_decision"] = decision.to_public_dict() if hasattr(decision, "to_public_dict") else None
                from agent.supervisor.autonomy_contract import append_decision_queue

                append_decision_queue(data, data.get("latest_decision"))
                if self._pipeline is not None:
                    risk_state = asdict(self._pipeline.risk_state)
                    risk_state["seen_keys"] = sorted(risk_state["seen_keys"])[-1000:]
                    data["signal_risk_state"] = risk_state
        except Exception:  # noqa: BLE001
            data["state"] = SupervisorState.ERROR.value
            data["last_error"] = "journal_write_failed"
            data["block_new_exposure"] = True
            self._save(data)
            return self.status(reason="journal_write_failed")
        data["last_candle_start"] = candle_start
        data["heartbeat_ms"] = now_ms
        data["last_action"] = action
        data["last_reason"] = result.get("reason")
        data["open_positions_seen"] = result["open_positions"]
        self._save(data)
        result["analysis_action"] = action
        result["risk_verdict"] = (decision.risk.verdict.value if hasattr(decision.risk.verdict, "value") else str(decision.risk.verdict)) if decision else "PROTECTIVE_ONLY"
        result["execution_allowed"] = False
        result["live_orders"] = False
        result["exchange_order_sent"] = False
        result["autonomous"] = True
        result["per_trade_approval"] = False
        result["state"] = data["state"]
        result["block_new_exposure"] = bool(data.get("block_new_exposure"))
        result["protective_monitoring"] = data["state"] in {"RUNNING", "PAUSED", "HALTED", "STOPPING"}
        result["duplicate"] = False
        return result

    def _risk_halt(self, trader: AutomaticPaperTrader, data: dict[str, Any], *, now_ms: int) -> str | None:
        from agent.paper.equity import utc_day_key
        from agent.supervisor.reports import journal_report

        report = journal_report(trader)
        equity = Decimal(report["equity"])
        peak = max(Decimal(str(data.get("peak_equity") or report["initial_balance"])), equity)
        day = utc_day_key(now_ms)
        if data.get("risk_day") != day:
            data["risk_day"] = day
            data["day_start_equity"] = str(equity)
        start = Decimal(str(data["day_start_equity"]))
        data["peak_equity"] = str(peak)
        data["daily_loss_fraction"] = str(max(Decimal("0"), (start - equity) / start)) if start > 0 else "0"
        data["drawdown_fraction"] = str(max(Decimal("0"), (peak - equity) / peak)) if peak > 0 else "0"
        if equity <= 0:
            return "EQUITY_EXHAUSTED"
        if Decimal(data["daily_loss_fraction"]) >= Decimal("0.03"):
            return "DAILY_LOSS_LIMIT"
        if Decimal(data["drawdown_fraction"]) >= Decimal("0.10"):
            return "DRAWDOWN_LIMIT"
        return None

    def _budget_allows_entry(self, price: float, auth: PaperSessionAuthorization | None) -> bool:
        if auth is None:
            return True
        # Research capital (≈5 USDT) must fit public linear minimums. Larger paper
        # sessions rely on PaperBrokerConfig exposure limits instead.
        if auth.capital_usdt > Decimal("10"):
            return True
        from agent.supervisor.experiment import assess_position_budget

        assessment = assess_position_budget(
            price=Decimal(str(price)),
            min_qty=Decimal("0.01"),
            qty_step=Decimal("0.01"),
            min_notional=Decimal("5"),
            capital=auth.capital_usdt,
            risk_fraction=auth.risk_fraction,
        )
        return bool(assessment.get("feasible"))

    def _decision(self, candles: list[Candle], *, symbol: str, category: str, interval: str, now_ms: int) -> Any:
        if self._evaluate is not None:
            return self._evaluate(
                symbol=symbol,
                category=category,
                interval=interval,
                candles=candles,
                now_ms=now_ms,
            )
        from agent.orchestrator.agent_registry import evaluate_decision
        from agent.multi_agent.config import PaperRiskConfig, SignalPipelineConfig
        from agent.multi_agent.pipeline import SignalPipeline
        from agent.multi_agent.risk_agent import SignalRiskState
        from agent.supervisor.reports import journal_report

        auth = self._current_authorization()
        equity = Decimal(journal_report(self._trader_open())["equity"])
        config = SignalPipelineConfig(risk=PaperRiskConfig(
            paper_balance=float(max(Decimal("0"), equity)),
            max_risk_fraction_per_trade=float(auth.risk_fraction) if auth else 0.01,
        ))
        if self._pipeline is None:
            memory = self._load().get("signal_risk_state") or {}
            memory["seen_keys"] = set(memory.get("seen_keys") or [])
            self._pipeline = SignalPipeline(config=config, risk_state=SignalRiskState(**memory), persist=False)
        else:
            self._pipeline.config = config

        return evaluate_decision(
            symbol=symbol,
            category=category,
            interval=interval,
            candles=candles,
            now_ms=now_ms,
            data_path="paper_supervisor",
            pipeline=self._pipeline,
        )

    def status(self, **extra: Any) -> dict[str, Any]:
        data = self._load()
        session_id = data.get("session_id")
        auth = data.get("authorization") if isinstance(data.get("authorization"), dict) else None
        if auth is None and self._authorization is not None:
            auth = self._authorization.to_dict()
        body = {
            "state": data.get("state") or SupervisorState.STOPPED.value,
            "session_id": session_id,
            "last_candle_start": data.get("last_candle_start"),
            "last_action": data.get("last_action"),
            "last_error": data.get("last_error"),
            "last_reason": data.get("last_reason"),
            "latest_decision": data.get("latest_decision"),
            "decision_queue": data.get("decision_queue") if isinstance(data.get("decision_queue"), list) else [],
            "heartbeat_ms": data.get("heartbeat_ms") or 0,
            "block_new_exposure": bool(data.get("block_new_exposure")),
            "protective_monitoring": data.get("state") in {"RUNNING", "PAUSED", "HALTED", "STOPPING"},
            "daily_loss_fraction": data.get("daily_loss_fraction"),
            "drawdown_fraction": data.get("drawdown_fraction"),
            "daily_loss_limit_fraction": "0.03",
            "drawdown_limit_fraction": "0.10",
            "live_orders": False,
            "execution_allowed": False,
            "exchange_order_sent": False,
            "mode": "PAPER",
            "autonomous": True,
            "per_trade_approval": False,
            "authorization": auth,
            "futures_shorting": "unsupported",
            "funding": "unsupported",
            "liquidation": "unsupported",
        }
        body.update(extra)
        return body

    def report(self) -> dict[str, Any]:
        from agent.supervisor.reports import journal_report

        if not self._load().get("session_id"):
            return {
                **self.status(),
                "available": False,
                "positions": [],
                "recent_trades": [],
                "recent_events": [],
                "pending_orders": [],
            }
        try:
            trader = self._trader_open()
            body = journal_report(trader)
            body.update(self.status())
            equity = Decimal(body["equity"])
            peak = Decimal(str(self._load().get("peak_equity") or body["initial_balance"]))
            body["loss_from_initial"] = body["drawdown"]
            body["drawdown"] = str(max(Decimal("0"), peak - equity))
            body["peak_equity"] = str(peak)
            return body
        except RuntimeError as exc:
            # Never 500 the ops desk — surface journal truth and keep status readable.
            reason = str(exc) or "journal_unavailable"
            return {
                **self.status(last_error=reason),
                "available": False,
                "equity_source": "paper_journal",
                "exchange_equity_included": False,
                "positions": [],
                "recent_trades": [],
                "recent_events": [],
                "pending_orders": [],
                "report_error": reason,
            }
