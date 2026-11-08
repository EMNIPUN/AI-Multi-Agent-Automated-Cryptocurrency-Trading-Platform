import os
import time
from datetime import datetime, timezone
from pathlib import Path

from pybit.unified_trading import HTTP

from apps.api.app.observability.types import ExecutionMode, ObservabilityEventType, PipelineStep

from agent.config import AgentSettings, live_orders_blocked
from agent.confirmed_candles import CandleFilterReject, filter_confirmed_candles
from agent.executor import OrderExecutor
from agent.intent_store import IntentStoreError
from agent.journal import TradeJournal
from agent.market_data import (
    PositionSnapshot,
    PositionStatus,
    fetch_candles,
    get_equity,
    get_position,
)
from agent.order_ids import account_fingerprint, env_scope_id
from agent.risk import RiskManager
from agent.signal_ids import correlation_id_from_signal
from agent.signal_ledger import ProcessedSignal, SignalLedger
from agent.strategies.base import SignalAction
from agent.strategies.ema_rsi import EmaRsiStrategy
from agent.strategies.evidence import evidence_payload
from agent.order_lifecycle_observer import OrderLifecycleObserver
from agent.telemetry_ledger import TelemetryLedger, make_event
from bot.config import API_KEY, USE_DEMO, USE_TESTNET, env_label, is_live_mainnet


class AgentRunner:
    def __init__(
        self,
        session: HTTP,
        settings: AgentSettings,
        *,
        signal_ledger: SignalLedger | None = None,
        signal_db_path: str | Path | None = None,
        telemetry: TelemetryLedger | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.strategy = EmaRsiStrategy(settings)
        self.journal = TradeJournal()
        self.executor = OrderExecutor(session, settings, self.journal)
        self.risk = RiskManager(
            settings,
            unresolved_intent_checker=self.executor.has_blocking_unresolved,
        )
        self.signal_ledger = signal_ledger or SignalLedger(db_path=signal_db_path)
        self.telemetry = telemetry
        self.env_scope = env_scope_id(use_testnet=USE_TESTNET, use_demo=USE_DEMO)
        self.account_fp = account_fingerprint(API_KEY)
        # Public non-secret binding id for telemetry isolation (never API key / account_fp).
        binding = (os.getenv("EXCHANGE_ACCOUNT_BINDING_ID") or "").strip()
        self.telemetry_scope_id = binding or "operator-local"
        self._order_observer = OrderLifecycleObserver(
            intent_store=self.executor.store,
            env_scope=self.env_scope,
            account_fp=self.account_fp,
            execution_mode=self._execution_mode(),
        )

        recovered = self.executor.recover_unresolved_on_startup()
        for intent in recovered:
            print(
                f"[recovery] intent {intent.client_order_id} -> "
                f"{intent.state.value} (no automatic resubmit)"
            )
            self.journal.write(
                "recovery",
                symbol=intent.symbol,
                category=intent.category,
                dry_run=False,
                reason="restart_unresolved_intent",
                details=f"{intent.client_order_id}:{intent.state.value}",
            )
        # ACCEPTED / PARTIAL survive restart and need evidence reconcile (read-only).
        for intent in self.executor.store.list_needs_reconcile(
            self.env_scope, self.account_fp
        ):
            if intent.state.value in {"ACCEPTED", "PARTIALLY_FILLED"}:
                print(
                    f"[recovery] pending fill evidence for {intent.client_order_id} "
                    f"state={intent.state.value} filled={intent.filled_qty or '0'} "
                    "(no cancel-all / flatten)"
                )
        view = self.risk.state
        print(
            f"[risk] mode={view.mode.value} date={view.risk_date or 'n/a'} "
            f"halted={view.halted} recovery_required={view.recovery_required}"
        )

    def _execution_mode(self) -> ExecutionMode:
        if self.settings.dry_run:
            return ExecutionMode.DRY_RUN
        if USE_TESTNET:
            return ExecutionMode.TESTNET
        return ExecutionMode.MAINNET_READONLY

    def _observe(
        self,
        event_type: ObservabilityEventType,
        *,
        event_id: str,
        message: str,
        symbol: str | None = None,
        interval: str | None = None,
        correlation_id: str | None = None,
        pipeline_step: PipelineStep | None = None,
        payload: dict | None = None,
    ) -> None:
        """Telemetry must never change execution. Failures are discarded."""
        if self.telemetry is None:
            return
        try:
            event = make_event(
                event_type=event_type,
                event_id=event_id,
                message=message,
                symbol=symbol,
                interval=interval,
                correlation_id=correlation_id,
                env_scope=self.env_scope,
                account_scope_label=self.telemetry_scope_id,
                execution_mode=self._execution_mode(),
                pipeline_step=pipeline_step,
                payload=payload or {},
            )
            self.telemetry.safe_record(event)
        except Exception:
            return

    def _status_line(self, equity: float | None) -> None:
        mode = "DRY-RUN" if self.settings.dry_run else "LIVE-ORDERS"
        if live_orders_blocked(self.settings) and not self.settings.dry_run:
            mode = "BLOCKED-MAINNET"
        eq = f"{equity:.4f}" if equity is not None else "n/a"
        print(
            f"\n[{datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC] "
            f"{env_label()} | {mode} | equity={eq} | "
            f"{self.settings.category} {','.join(self.settings.symbols)} | "
            f"tf={self.settings.interval} poll={self.settings.poll_seconds}s"
        )

    def _now_ms(self) -> int:
        return int(datetime.now(timezone.utc).timestamp() * 1000)

    def tick(self) -> bool:
        """Run one evaluation cycle. Returns False if agent should stop."""
        if not self.settings.enabled:
            print("AGENT_ENABLED=false — stopping.")
            return False

        equity = get_equity(self.session)
        self.risk.update_equity(equity)
        self._status_line(equity)
        tick_id = str(self._now_ms())
        primary = self.settings.symbols[0] if self.settings.symbols else None
        self._observe(
            ObservabilityEventType.AGENT_HEARTBEAT,
            event_id=f"agent.heartbeat:{self.env_scope}:{tick_id}",
            message="Worker tick started",
            symbol=primary,
            interval=self.settings.interval,
            pipeline_step=PipelineStep.MARKET_DATA,
            payload={"dry_run": self.settings.dry_run},
        )

        if not self.settings.dry_run:
            try:
                self.executor.reconcile_unresolved()
            except IntentStoreError as exc:
                # Fail closed for new exposure; do not reset Phase 1C HALTED.
                print(f"RECONCILE STORE ERROR (fail closed): {exc}")
                self.journal.write(
                    "error",
                    reason="reconcile_store_unavailable",
                    dry_run=False,
                    details=str(exc),
                    equity="" if equity is None else f"{equity:.8f}",
                )

        risk_view = self.risk.state
        if risk_view.halted:
            print("KILL SWITCH:", risk_view.halt_reason)
            self.journal.write(
                "halt",
                reason=risk_view.halt_reason,
                equity="" if equity is None else f"{equity:.8f}",
                dry_run=self.settings.dry_run,
                details=f"mode={risk_view.mode.value}; durable=1",
            )
            self._observe(
                ObservabilityEventType.RISK_HALTED,
                event_id=f"risk.halted:{self.env_scope}:{tick_id}",
                message=risk_view.halt_reason or "risk halted",
                pipeline_step=PipelineStep.HALTED,
                payload={"mode": risk_view.mode.value},
            )
            return False
        if risk_view.recovery_required:
            print(
                "RISK RECOVERY_REQUIRED — new exposure blocked:",
                risk_view.halt_reason or risk_view.mode.value,
            )
            self.journal.write(
                "blocked",
                reason=risk_view.halt_reason or "recovery_required",
                equity="" if equity is None else f"{equity:.8f}",
                dry_run=self.settings.dry_run,
                details=f"mode={risk_view.mode.value}",
            )

        positions: dict[str, PositionSnapshot] = {}
        for symbol in self.settings.symbols:
            positions[symbol] = get_position(
                self.session,
                self.settings.category,
                symbol,
            )

        open_count = self.risk.open_position_count(positions)
        now_ms = self._now_ms()
        staleness = (
            self.settings.max_candle_staleness_ms
            if self.settings.max_candle_staleness_ms > 0
            else None
        )

        for symbol in self.settings.symbols:
            try:
                raw_candles = fetch_candles(
                    self.session,
                    self.settings.category,
                    symbol,
                    self.settings.interval,
                    self.settings.candle_limit,
                )
            except Exception as exc:
                print(f"[{symbol}] candle error:", type(exc).__name__)
                self.journal.write(
                    "blocked",
                    symbol=symbol,
                    category=self.settings.category,
                    dry_run=self.settings.dry_run,
                    reason=f"candle_fetch_failed:{type(exc).__name__}",
                    equity="" if equity is None else f"{equity:.8f}",
                    details="new_entries_skipped",
                )
                self._observe(
                    ObservabilityEventType.AGENT_ERROR,
                    event_id=f"agent.error:candle:{symbol}:{tick_id}",
                    message=f"Candle fetch failed: {type(exc).__name__}",
                    symbol=symbol,
                    interval=self.settings.interval,
                    payload={"error_type": type(exc).__name__},
                )
                continue

            filtered = filter_confirmed_candles(
                raw_candles,
                self.settings.interval,
                now_ms=now_ms,
                grace_ms=self.settings.candle_finalize_grace_ms,
                max_clock_skew_ms=self.settings.max_clock_skew_ms,
                max_staleness_ms=staleness,
                min_bars=self.strategy.min_confirmed_bars(),
            )
            if isinstance(filtered, CandleFilterReject):
                print(f"[{symbol}] market data rejected: {filtered.reason}")
                self.journal.write(
                    "blocked",
                    symbol=symbol,
                    category=self.settings.category,
                    dry_run=self.settings.dry_run,
                    reason=filtered.reason,
                    equity="" if equity is None else f"{equity:.8f}",
                    details="confirmed_candle_filter; new_entries_skipped",
                )
                continue

            last_bar = filtered.candles[-1]
            self._observe(
                ObservabilityEventType.MARKET_CANDLE_CONFIRMED,
                event_id=f"market.candle_confirmed:{symbol}:{filtered.newest_close_ms}",
                message="Confirmed candle accepted",
                symbol=symbol,
                interval=filtered.interval,
                pipeline_step=PipelineStep.CONFIRMED_CANDLE,
                payload={
                    "candle_close_at": datetime.fromtimestamp(
                        filtered.newest_close_ms / 1000, tz=timezone.utc
                    ).isoformat(),
                    "candle_start_ms": last_bar.start,
                    "candle_close_ms": filtered.newest_close_ms,
                    "open": last_bar.open,
                    "high": last_bar.high,
                    "low": last_bar.low,
                    "close": last_bar.close,
                    "volume": last_bar.volume,
                    # Compact recent confirmed closes for chart correlation (not invented).
                    "recent_bars": [
                        {
                            "time": int(c.start // 1000),
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in filtered.candles[-40:]
                    ],
                },
            )
            signal = self.strategy.evaluate(
                filtered.candles,
                interval=filtered.interval,
                symbol=symbol,
                category=self.settings.category,
            )
            snapshot = positions[symbol]
            if snapshot.status is PositionStatus.OPEN and snapshot.position:
                pos = snapshot.position
                pos_txt = f"{pos['side']} {pos['size']}"
            elif snapshot.status is PositionStatus.FLAT:
                pos_txt = "flat"
            else:
                pos_txt = f"UNKNOWN ({snapshot.reason})"

            print(
                f"[{symbol}] signal={signal.action.value} pos={pos_txt} "
                f"| confirmed_bars={len(filtered.candles)} "
                f"forming_skipped={filtered.skipped_forming} | {signal.reason}"
            )
            self.journal.write(
                "signal",
                symbol=symbol,
                category=self.settings.category,
                dry_run=self.settings.dry_run,
                reason=signal.reason,
                price=str(signal.price),
                equity="" if equity is None else f"{equity:.8f}",
                details=(
                    f"{signal.action.value}; close_ms={signal.candle_close_ms}; "
                    f"sid={signal.signal_id or '-'}"
                ),
            )
            evidence = evidence_payload(signal, self.settings)
            self._observe(
                ObservabilityEventType.ANALYSIS_COMPLETED,
                event_id=f"analysis.completed:{symbol}:{signal.candle_close_ms or tick_id}",
                message="EMA/RSI analysis completed",
                symbol=symbol,
                interval=filtered.interval,
                correlation_id=signal.signal_id or None,
                pipeline_step=PipelineStep.STRATEGY,
                payload=evidence,
            )
            self._observe(
                ObservabilityEventType.SIGNAL_GENERATED,
                event_id=f"signal.generated:{symbol}:{signal.signal_id or signal.candle_close_ms or tick_id}:{signal.action.value}",
                message=signal.reason,
                symbol=symbol,
                interval=filtered.interval,
                correlation_id=signal.signal_id or None,
                pipeline_step=PipelineStep.SIGNAL,
                payload={
                    "action": signal.action.value,
                    "price": signal.price,
                    **evidence,
                },
            )

            if snapshot.status is PositionStatus.UNKNOWN:
                print(
                    f"[{symbol}] BLOCKED new exposure: position state UNKNOWN — "
                    f"{snapshot.reason}"
                )
                self.journal.write(
                    "blocked",
                    symbol=symbol,
                    category=self.settings.category,
                    dry_run=self.settings.dry_run,
                    reason=snapshot.reason,
                    equity="" if equity is None else f"{equity:.8f}",
                    details="position_state=UNKNOWN; new_entries_rejected",
                )
                self._observe(
                    ObservabilityEventType.RISK_BLOCKED,
                    event_id=f"risk.blocked:unknown:{symbol}:{tick_id}",
                    message=snapshot.reason or "position state unknown",
                    symbol=symbol,
                    interval=filtered.interval,
                    pipeline_step=PipelineStep.BLOCKED,
                    payload={"position_status": "UNKNOWN"},
                )
                continue

            # HOLD is analysis-only; not ledgered as actionable.
            if signal.action is SignalAction.HOLD:
                continue

            if not signal.signal_id or signal.candle_close_ms <= 0:
                self.journal.write(
                    "blocked",
                    symbol=symbol,
                    category=self.settings.category,
                    dry_run=self.settings.dry_run,
                    reason="actionable_signal_missing_identity",
                    equity="" if equity is None else f"{equity:.8f}",
                )
                continue

            if self.signal_ledger.has_processed(
                self.env_scope, self.account_fp, signal.signal_id
            ):
                print(
                    f"[{symbol}] skip duplicate signal {signal.signal_id} "
                    f"(close_ms={signal.candle_close_ms})"
                )
                self.journal.write(
                    "idempotent_skip",
                    symbol=symbol,
                    category=self.settings.category,
                    dry_run=self.settings.dry_run,
                    reason="signal_already_processed",
                    details=signal.signal_id,
                    equity="" if equity is None else f"{equity:.8f}",
                )
                continue

            plan = self.risk.plan_trade(
                self.session,
                symbol,
                signal,
                snapshot,
                equity,
                open_count,
            )
            if not plan:
                self._observe(
                    ObservabilityEventType.RISK_BLOCKED,
                    event_id=f"risk.blocked:plan:{symbol}:{signal.signal_id}",
                    message="Risk did not produce a trade plan",
                    symbol=symbol,
                    interval=filtered.interval,
                    correlation_id=signal.signal_id,
                    pipeline_step=PipelineStep.BLOCKED,
                )
                continue

            self._observe(
                ObservabilityEventType.RISK_APPROVED,
                event_id=f"risk.approved:{symbol}:{signal.signal_id}",
                message=plan.reason or "Risk approved trade plan",
                symbol=symbol,
                interval=filtered.interval,
                correlation_id=correlation_id_from_signal(signal.signal_id),
                pipeline_step=PipelineStep.RISK,
                payload={"reduce_only": plan.reduce_only, "side": plan.side},
            )

            # Bind Phase 1B intent correlation to durable signal identity.
            from dataclasses import replace

            plan = replace(
                plan,
                correlation_id=correlation_id_from_signal(signal.signal_id),
                risk_auth_ref=plan.risk_auth_ref or f"sig:{signal.signal_id[:24]}",
            )

            ok = self.executor.execute(plan, equity)
            if ok:
                self.signal_ledger.mark_processed(
                    env_scope=self.env_scope,
                    account_fp=self.account_fp,
                    signal=ProcessedSignal(
                        signal_id=signal.signal_id,
                        symbol=symbol,
                        category=self.settings.category,
                        interval=filtered.interval,
                        action=signal.action.value,
                        candle_close_ms=signal.candle_close_ms,
                    ),
                )
                if not plan.reduce_only:
                    open_count += 1
                else:
                    open_count = max(0, open_count - 1)

        self._publish_order_lifecycle()
        return True

    def _publish_order_lifecycle(self) -> None:
        """Read intent store and project evidenced transitions. Never mutates authority."""
        if self.telemetry is None:
            return
        try:
            self._order_observer.execution_mode = self._execution_mode()
            self._order_observer.poll(self.telemetry)
        except Exception:
            return

    def run_forever(self) -> None:
        print("=== Bybit Automated Trading Agent ===")
        print(f"Environment: {env_label()}")
        print(f"Dry-run: {self.settings.dry_run}")
        if is_live_mainnet():
            print("WARNING: Bybit env is MAINNET.")
            if not self.settings.allow_live:
                print(
                    "Live agent orders on mainnet are blocked "
                    "unless AGENT_ALLOW_LIVE=true."
                )
        print(f"Journal: {self.journal.path}")
        print("Ctrl+C to stop.\n")

        self.journal.write(
            "start",
            category=self.settings.category,
            dry_run=self.settings.dry_run,
            reason="agent started",
            details=",".join(self.settings.symbols),
        )
        self._observe(
            ObservabilityEventType.AGENT_STARTED,
            event_id=f"agent.started:{self.env_scope}:{self._now_ms()}",
            message="Agent process started",
            symbol=self.settings.symbols[0] if self.settings.symbols else None,
            interval=self.settings.interval,
            payload={"dry_run": self.settings.dry_run},
        )

        try:
            while True:
                if not self.tick():
                    break
                time.sleep(self.settings.poll_seconds)
        except KeyboardInterrupt:
            print("\nAgent stopped by user.")
            self.journal.write(
                "stop",
                dry_run=self.settings.dry_run,
                reason="keyboard interrupt",
            )
            self._observe(
                ObservabilityEventType.AGENT_STOPPED,
                event_id=f"agent.stopped:{self.env_scope}:{self._now_ms()}",
                message="Agent stopped by operator",
            )
