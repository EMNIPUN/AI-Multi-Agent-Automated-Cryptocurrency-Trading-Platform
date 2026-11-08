"""
Phase 6A automated execution pipeline (mock-first, gated).

Confirmed signal → execution risk → durable intent → (gated) Testnet order
→ ack ≠ fill → fill reconcile → protective verify → audit.

Default mode SIGNALS_ONLY never submits. Real Mainnet path does not exist.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass
from typing import Any

from agent.automation.execution_risk import (
    ExecutionCandidate,
    ExecutionRiskAssessment,
    ExecutionRiskLimits,
    ExecutionRiskState,
    ExecutionRiskVerdict,
    evaluate_execution_risk,
    record_api_error,
)
from agent.automation.exec_store import AutomationExecStore, ExecutionIntentRow
from agent.automation.modes import (
    AutomationGateError,
    TradingMode,
    get_automation_gates,
)
from agent.automation.protective import (
    apply_and_verify_protection,
    emergency_risk_procedure,
)
from agent.automation.testnet_adapter import (
    BybitTestnetTradingAdapter,
    MockBybitTestnetAdapter,
)


@dataclass(frozen=True)
class SignalExecutionRequest:
    """Bridge input from multi-agent decision — does not flip execution_allowed on signals."""

    decision_id: str
    symbol: str
    category: str
    side: str  # Buy / Sell
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    strategy_version: str
    correlation_id: str = ""
    data_age_ms: int = 0
    spread_bps: float = 0.0
    intended_notional: float = 100.0


@dataclass(frozen=True)
class PipelineResult:
    mode: str
    submitted: bool
    state: str
    intent_id: str | None
    client_order_id: str | None
    exchange_order_id: str | None
    filled: bool
    protection_state: str | None
    risk: dict[str, Any]
    detail: str
    emergency: dict[str, str] | None = None
    execution_allowed: bool = False
    trading_enabled: bool = False


class AutomatedExecutionPipeline:
    def __init__(
        self,
        *,
        adapter: BybitTestnetTradingAdapter | None = None,
        store: AutomationExecStore | None = None,
        risk_state: ExecutionRiskState | None = None,
        limits: ExecutionRiskLimits | None = None,
        simulate_fills: bool = False,
    ) -> None:
        self.adapter = adapter or MockBybitTestnetAdapter()
        self.store = store or AutomationExecStore()
        self.risk_state = risk_state or ExecutionRiskState()
        self.limits = limits or ExecutionRiskLimits()
        self.simulate_fills = simulate_fills

    def process(self, req: SignalExecutionRequest, *, now_ms: int | None = None) -> PipelineResult:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        gates = get_automation_gates()

        if gates.mode is TradingMode.SIGNALS_ONLY:
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="SIGNALS_ONLY",
                intent_id=None,
                client_order_id=None,
                exchange_order_id=None,
                filled=False,
                protection_state=None,
                risk={"verdict": "SKIPPED", "reason_codes": ["SIGNALS_ONLY"]},
                detail="Automation in SIGNALS_ONLY — no execution intent submitted",
            )

        if gates.mode is TradingMode.MAINNET_TRADING or gates.mainnet_trading_enabled:
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="MAINNET_LOCKED",
                intent_id=None,
                client_order_id=None,
                exchange_order_id=None,
                filled=False,
                protection_state=None,
                risk={"verdict": "VETO", "reason_codes": ["MAINNET_LOCKED"]},
                detail="MAINNET_TRADING has no execution path in Phase 6A",
            )

        if req.category == "linear" and not gates.perpetual_auto_execution_enabled:
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="LINEAR_DISABLED",
                intent_id=None,
                client_order_id=None,
                exchange_order_id=None,
                filled=False,
                protection_state=None,
                risk={"verdict": "VETO", "reason_codes": ["LINEAR_AUTO_DISABLED"]},
                detail="USDT perpetual auto-execution disabled until separately approved",
            )

        bal = self.adapter.get_balance()
        client_order_id = self._client_order_id(req)
        intent_id = f"ei_{hashlib.sha256(client_order_id.encode()).hexdigest()[:24]}"

        # Idempotent: existing intent short-circuits duplicate submission.
        existing = self.store.get_by_client_order_id(client_order_id)
        if existing is not None:
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state=existing.state,
                intent_id=existing.intent_id,
                client_order_id=existing.client_order_id,
                exchange_order_id=existing.exchange_order_id,
                filled=existing.state == "FILLED",
                protection_state=existing.protection_state,
                risk={"verdict": "SKIPPED", "reason_codes": ["DUPLICATE_INTENT"]},
                detail="Duplicate client_order_id — durable intent already exists",
            )

        assessment = evaluate_execution_risk(
            ExecutionCandidate(
                symbol=req.symbol,
                category=req.category,
                side=req.side,
                entry_price=req.entry_price,
                stop_loss=req.stop_loss,
                take_profit=req.take_profit,
                equity=bal.total_equity,
                available_balance=bal.available_balance,
                spread_bps=req.spread_bps,
                data_age_ms=req.data_age_ms,
                client_order_id=client_order_id,
                intended_notional=req.intended_notional,
                now_ms=now,
            ),
            self.risk_state,
            self.limits,
        )
        if assessment.verdict is not ExecutionRiskVerdict.APPROVED:
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="RISK_BLOCKED",
                intent_id=None,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state=None,
                risk={
                    "verdict": assessment.verdict.value,
                    "reason_codes": list(assessment.reason_codes),
                    "explanation": assessment.explanation,
                },
                detail=assessment.explanation,
                emergency=(
                    emergency_risk_procedure(assessment.explanation)
                    if assessment.verdict is ExecutionRiskVerdict.HALTED
                    else None
                ),
            )

        instr = self.adapter.get_instrument(category=req.category, symbol=req.symbol)
        qty = float(assessment.sized_qty or 0.0)
        # Snap to step / min
        if instr.qty_step > 0:
            qty = (qty // instr.qty_step) * instr.qty_step
        if qty < instr.min_order_qty:
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="SIZE_TOO_SMALL",
                intent_id=None,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state=None,
                risk={"verdict": "VETO", "reason_codes": ["MIN_ORDER_QTY"]},
                detail="Sized qty below instrument minimum",
            )

        qty_s = f"{qty:.8f}".rstrip("0").rstrip(".")
        sl_s = f"{req.stop_loss}" if req.stop_loss is not None else None
        tp_s = f"{req.take_profit}" if req.take_profit is not None else None

        row = ExecutionIntentRow(
            intent_id=intent_id,
            client_order_id=client_order_id,
            decision_id=req.decision_id,
            symbol=req.symbol.upper(),
            category=req.category,
            side=req.side,
            qty=qty_s,
            state="CREATED",
            exchange_order_id=None,
            stop_loss=sl_s,
            take_profit=tp_s,
            protection_state="PENDING",
            payload={
                "strategy_version": req.strategy_version,
                "correlation_id": req.correlation_id,
                "ack_is_not_fill": True,
            },
        )
        if not self.store.insert_intent(row, now_ms=now):
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="INTENT_RACE",
                intent_id=intent_id,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state=None,
                risk={"verdict": "SKIPPED", "reason_codes": ["INTENT_INSERT_RACE"]},
                detail="Intent insert lost race — treat as duplicate",
            )

        if gates.mode is TradingMode.PAPER_TRADING:
            self.store.update_intent(intent_id, state="PAPER_SIMULATED", now_ms=now)
            self.store.append_event(
                intent_id=intent_id,
                event_type="paper_simulated",
                detail={"qty": qty_s},
                now_ms=now,
            )
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="PAPER_SIMULATED",
                intent_id=intent_id,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state="N/A",
                risk={
                    "verdict": assessment.verdict.value,
                    "reason_codes": list(assessment.reason_codes),
                },
                detail="PAPER_TRADING — no exchange order",
            )

        # TESTNET_TRADING path — still requires order_submission_allowed.
        self.store.update_intent(intent_id, state="SUBMISSION_PENDING", now_ms=now)
        try:
            ack = self.adapter.place_order(
                category=req.category,
                symbol=req.symbol.upper(),
                side=req.side,
                orderType="Market",
                qty=qty_s,
                orderLinkId=client_order_id,
            )
        except AutomationGateError as exc:
            self.store.update_intent(intent_id, state="BLOCKED_BY_GATE", now_ms=now)
            self.store.append_event(
                intent_id=intent_id,
                event_type="gate_blocked",
                detail={"error": str(exc)},
                now_ms=now,
            )
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="BLOCKED_BY_GATE",
                intent_id=intent_id,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state="PENDING",
                risk={
                    "verdict": assessment.verdict.value,
                    "reason_codes": list(assessment.reason_codes),
                },
                detail=str(exc),
            )
        except TimeoutError as exc:
            record_api_error(self.risk_state)
            self.store.update_intent(
                intent_id, state="RECONCILIATION_REQUIRED", now_ms=now
            )
            self.store.append_event(
                intent_id=intent_id,
                event_type="ambiguous_timeout",
                detail={"error": str(exc)},
                now_ms=now,
            )
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="RECONCILIATION_REQUIRED",
                intent_id=intent_id,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state="PENDING",
                risk={"verdict": "UNKNOWN", "reason_codes": ["AMBIGUOUS_TIMEOUT"]},
                detail="Timeout after possible submit — reconcile; do not resubmit blindly",
                emergency=emergency_risk_procedure("ambiguous_order_timeout"),
            )
        except Exception as exc:  # noqa: BLE001
            record_api_error(self.risk_state)
            self.store.update_intent(intent_id, state="UNKNOWN", now_ms=now)
            return PipelineResult(
                mode=gates.mode.value,
                submitted=False,
                state="UNKNOWN",
                intent_id=intent_id,
                client_order_id=client_order_id,
                exchange_order_id=None,
                filled=False,
                protection_state="PENDING",
                risk={"verdict": "UNKNOWN", "reason_codes": ["PLACE_EXCEPTION"]},
                detail=type(exc).__name__,
            )

        # Acknowledgement only.
        self.risk_state.seen_client_order_ids.add(client_order_id)
        self.store.update_intent(
            intent_id,
            state="ACCEPTED",
            exchange_order_id=ack.exchange_order_id,
            now_ms=now,
        )
        self.store.append_event(
            intent_id=intent_id,
            event_type="order_ack",
            detail={"exchange_order_id": ack.exchange_order_id, "ack_is_not_fill": True},
            now_ms=now,
        )

        filled = False
        protection_state = "PENDING"
        if self.simulate_fills and isinstance(self.adapter, MockBybitTestnetAdapter):
            fill = self.adapter.simulate_full_fill(
                client_order_id=client_order_id, price=req.entry_price
            )
            self.store.update_intent(intent_id, state="FILLED", now_ms=now)
            self.store.append_event(
                intent_id=intent_id,
                event_type="fill_proven",
                detail={"exec_id": fill.exec_id, "qty": fill.qty},
                now_ms=now,
            )
            filled = True
            prot = apply_and_verify_protection(
                self.adapter,
                symbol=req.symbol,
                category=req.category,
                stop_loss=sl_s,
                take_profit=tp_s,
                risk_state=self.risk_state,
            )
            protection_state = prot.state.value
            self.store.update_intent(
                intent_id, protection_state=protection_state, now_ms=now
            )
            if prot.state.value != "VERIFIED":
                return PipelineResult(
                    mode=gates.mode.value,
                    submitted=True,
                    state="FILLED",
                    intent_id=intent_id,
                    client_order_id=client_order_id,
                    exchange_order_id=ack.exchange_order_id,
                    filled=True,
                    protection_state=protection_state,
                    risk={
                        "verdict": assessment.verdict.value,
                        "reason_codes": list(assessment.reason_codes),
                    },
                    detail="Fill proven but protection not verified — entries halted",
                    emergency=emergency_risk_procedure(prot.detail),
                    execution_allowed=False,
                )

        return PipelineResult(
            mode=gates.mode.value,
            submitted=True,
            state="ACCEPTED" if not filled else "FILLED",
            intent_id=intent_id,
            client_order_id=client_order_id,
            exchange_order_id=ack.exchange_order_id,
            filled=filled,
            protection_state=protection_state,
            risk={
                "verdict": assessment.verdict.value,
                "reason_codes": list(assessment.reason_codes),
                "sized_qty": assessment.sized_qty,
            },
            detail=(
                "Order acknowledged — not a confirmed fill"
                if not filled
                else "Mock fill + protection verified"
            ),
            execution_allowed=False,
        )

    @staticmethod
    def _client_order_id(req: SignalExecutionRequest) -> str:
        raw = f"{req.decision_id}|{req.symbol}|{req.side}|{req.category}|{req.strategy_version}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]
        # Bybit orderLinkId constraints — alphanumeric-ish short id.
        return f"cn6a{digest}"


def status_bundle(store: AutomationExecStore | None = None) -> dict[str, Any]:
    from agent.automation.modes import gates_public_dict

    st = store or AutomationExecStore()
    return {
        **gates_public_dict(),
        "local_execution": st.status_summary(),
        "supabase_execution_writes": False,
        "phase": "6A",
        "private_ws": "designed_not_implemented",
        "spot_first": True,
        "linear_auto_disabled_until_approved": True,
    }
