"""Order execution with durable idempotent intents (Phase 1B)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pybit.unified_trading import HTTP

from agent.config import AgentSettings, live_orders_blocked
from agent.intent_store import IntentStore, IntentStoreError
from agent.journal import TradeJournal
from agent.order_ids import (
    account_fingerprint,
    build_client_order_id,
    build_intent_id,
    env_scope_id,
    intent_fingerprint,
    validate_order_link_id,
)
from agent.order_intent import (
    OrderIntent,
    OrderIntentState,
    default_expiry_iso,
    utc_now_iso,
)
from agent.reconcile import reconcile_intent
from agent.risk import TradePlan
from bot.client import create_write_session
from bot.config import API_KEY, USE_DEMO, USE_TESTNET


class OrderExecutor:
    def __init__(
        self,
        session: HTTP,
        settings: AgentSettings,
        journal: TradeJournal,
        *,
        store: IntentStore | None = None,
        write_session: HTTP | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.journal = journal
        self.store = store or IntentStore(db_path=db_path)
        self._write_session = write_session
        self.env_scope = env_scope_id(use_testnet=USE_TESTNET, use_demo=USE_DEMO)
        self.account_fp = account_fingerprint(API_KEY)

    @property
    def write_session(self) -> HTTP:
        if self._write_session is None:
            self._write_session = create_write_session()
        return self._write_session

    def recover_unresolved_on_startup(self) -> list[OrderIntent]:
        """
        Mark mid-flight submissions for reconcile. ACCEPTED / PARTIAL rows
        stay put and are picked up by list_needs_reconcile (no blind resubmit).
        Does not create/amend/cancel exchange orders. Does not reset Phase 1C halt.
        """
        return self.store.mark_restart_recovery(self.env_scope, self.account_fp)

    def has_blocking_unresolved(
        self, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        """Unresolved + partial fills block new exposure (fail closed)."""
        return self.store.list_blocking_exposure(
            self.env_scope, self.account_fp, symbol=symbol
        )

    def reconcile_unresolved(self, *, symbol: str | None = None) -> list[OrderIntent]:
        """
        Read-only evidence reconcile for unresolved, ACCEPTED, and PARTIAL intents.

        On IntentStoreError / conflict with store_error, leave intents blocking
        and re-raise so the runner can fail closed — never auto-reset HALTED.
        """
        pending = self.store.list_needs_reconcile(
            self.env_scope, self.account_fp, symbol=symbol
        )
        out: list[OrderIntent] = []
        for intent in pending:
            result = reconcile_intent(self.session, self.store, intent)
            out.append(result.intent)
            self.journal.write(
                "reconcile",
                symbol=intent.symbol,
                category=intent.category,
                dry_run=False,
                reason=result.detail,
                order_id=result.intent.exchange_order_id,
                details=(
                    f"proven={result.proven}; conflict={result.conflict}; "
                    f"store_error={result.store_error}; "
                    f"state={result.intent.state.value}; "
                    f"filled={result.intent.filled_qty}; "
                    f"link={intent.client_order_id}"
                ),
            )
            if result.store_error:
                raise IntentStoreError(
                    f"reconcile store unavailable for {intent.client_order_id}"
                )
        return out

    def ensure_leverage(self, symbol: str) -> None:
        if self.settings.category != "linear":
            return
        if self.settings.dry_run:
            return
        lev = str(self.settings.leverage)
        try:
            response = self.write_session.set_leverage(
                category="linear",
                symbol=symbol,
                buyLeverage=lev,
                sellLeverage=lev,
            )
            code = response.get("retCode")
            if code not in (0, 110043):
                print(f"[{symbol}] set leverage warning:", response.get("retMsg"))
        except Exception as exc:
            print(f"[{symbol}] set leverage failed:", type(exc).__name__)

    def _correlation_id(self, plan: TradePlan) -> str:
        if plan.correlation_id.strip():
            return plan.correlation_id.strip()
        raw = f"{plan.symbol}|{plan.side}|{plan.qty}|{plan.reduce_only}|{plan.reason}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]

    def build_intent(self, plan: TradePlan, *, dry_run: bool) -> OrderIntent:
        corr = self._correlation_id(plan)
        risk_ref = plan.risk_auth_ref or f"risk:{corr}"
        fp = intent_fingerprint(
            env_scope=self.env_scope,
            account_fp=self.account_fp,
            category=self.settings.category,
            symbol=plan.symbol,
            side=plan.side,
            qty=plan.qty,
            reduce_only=plan.reduce_only,
            take_profit=plan.take_profit,
            stop_loss=plan.stop_loss,
            correlation_id=corr,
        )
        client_order_id = build_client_order_id(fp)
        if not validate_order_link_id(client_order_id):
            raise ValueError("invalid client_order_id")
        return OrderIntent(
            intent_id=build_intent_id(fp),
            client_order_id=client_order_id,
            env_scope=self.env_scope,
            account_fp=self.account_fp,
            symbol=plan.symbol,
            category=self.settings.category,
            side=plan.side,
            qty=plan.qty,
            reduce_only=plan.reduce_only,
            order_type="Market",
            time_in_force="IOC",
            take_profit=plan.take_profit,
            stop_loss=plan.stop_loss,
            correlation_id=corr,
            risk_auth_ref=risk_ref,
            state=OrderIntentState.CREATED,
            created_at=utc_now_iso(),
            expires_at=default_expiry_iso(),
            dry_run=dry_run,
        )

    def _place_params(self, intent: OrderIntent) -> dict:
        params: dict = {
            "category": intent.category,
            "symbol": intent.symbol,
            "side": intent.side,
            "orderType": intent.order_type,
            "qty": intent.qty,
            "timeInForce": intent.time_in_force,
            "orderLinkId": intent.client_order_id,
        }
        if intent.category == "linear":
            params["positionIdx"] = 0
            if intent.reduce_only:
                params["reduceOnly"] = True
            if intent.take_profit and not intent.reduce_only:
                params["takeProfit"] = intent.take_profit
            if intent.stop_loss and not intent.reduce_only:
                params["stopLoss"] = intent.stop_loss
        return params

    def execute(self, plan: TradePlan, equity: float | None) -> bool:
        block = live_orders_blocked(self.settings)
        dry = self.settings.dry_run or block is not None
        if block and not self.settings.dry_run:
            print(f"BLOCKED: {block}")
            self.journal.write(
                "blocked",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=True,
                reason=block,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False

        # Exposure-increasing live orders blocked while unresolved intents exist.
        if not dry and not plan.reduce_only:
            unresolved = self.has_blocking_unresolved()
            if unresolved:
                reason = (
                    f"unresolved order intent(s) require reconciliation "
                    f"({unresolved[0].client_order_id} state={unresolved[0].state.value})"
                )
                print(f"[{plan.symbol}] BLOCKED: {reason}")
                self.journal.write(
                    "blocked",
                    symbol=plan.symbol,
                    category=self.settings.category,
                    side=plan.side,
                    qty=plan.qty,
                    dry_run=False,
                    reason=reason,
                    equity="" if equity is None else f"{equity:.8f}",
                    details="incident=unresolved_intent_blocks_new_exposure",
                )
                return False

        summary = (
            f"{plan.side} {plan.qty} {plan.symbol} "
            f"{'(reduceOnly) ' if plan.reduce_only else ''}"
            f"TP={plan.take_profit or '-'} SL={plan.stop_loss or '-'}"
        )

        intent = self.build_intent(plan, dry_run=dry)
        inserted, stored = self.store.insert_created(intent)

        if not inserted:
            # Same client_order_id already persisted — never create a second submission.
            print(
                f"[{plan.symbol}] idempotent hit: existing intent "
                f"{stored.client_order_id} state={stored.state.value}"
            )
            self.journal.write(
                "idempotent_skip",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=stored.dry_run,
                reason=f"existing_intent_state={stored.state.value}",
                order_id=stored.exchange_order_id,
                equity="" if equity is None else f"{equity:.8f}",
                details=stored.client_order_id,
            )
            if stored.state in {
                OrderIntentState.ACCEPTED,
                OrderIntentState.PARTIALLY_FILLED,
                OrderIntentState.FILLED,
            }:
                return True
            if stored.state in {
                OrderIntentState.SUBMISSION_PENDING,
                OrderIntentState.UNKNOWN,
                OrderIntentState.RECONCILIATION_REQUIRED,
            }:
                # Do not blind-retry; leave for reconciliation.
                return False
            if stored.state is OrderIntentState.CREATED and not stored.dry_run:
                # Prior crash before claim — allow claim path below using stored id.
                intent = stored
            else:
                return stored.state is OrderIntentState.CANCELED and stored.dry_run

        if dry:
            print(
                f"[DRY-RUN] Intent recorded (not submitted, not filled): "
                f"{summary} | link={stored.client_order_id} | {plan.reason}"
            )
            self.store.transition(
                stored.intent_id,
                OrderIntentState.CANCELED,
                last_error="dry_run_not_submitted",
            )
            self.journal.write(
                "dry_run",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=True,
                reason=plan.reason,
                equity="" if equity is None else f"{equity:.8f}",
                details=f"{summary}; link={stored.client_order_id}; not_filled",
            )
            return True

        claimed = self.store.try_claim_for_submission(stored.intent_id)
        if claimed is None:
            again = self.store.get_by_intent_id(stored.intent_id)
            print(
                f"[{plan.symbol}] submission claim failed "
                f"(state={again.state.value if again else 'missing'}) — no retry"
            )
            self.journal.write(
                "blocked",
                symbol=plan.symbol,
                category=self.settings.category,
                dry_run=False,
                reason="could_not_claim_for_submission",
                details=stored.client_order_id,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False

        self.ensure_leverage(plan.symbol)
        params = self._place_params(claimed)

        # Single attempt only — write session has force_retry=False.
        try:
            response = self.write_session.place_order(**params)
        except TimeoutError as exc:
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.UNKNOWN,
                last_error=f"timeout_after_possible_accept:{type(exc).__name__}",
                submission_attempted=True,
            )
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.RECONCILIATION_REQUIRED,
                last_error="timeout: reconciliation required (not assumed failed)",
            )
            print(
                f"[{plan.symbol}] order timeout — marked RECONCILIATION_REQUIRED; "
                "will not auto-resubmit"
            )
            self.journal.write(
                "error",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=False,
                reason="timeout_ambiguous_submission",
                details=claimed.client_order_id,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False
        except OSError as exc:
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.UNKNOWN,
                last_error=f"network:{type(exc).__name__}",
                submission_attempted=True,
            )
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.RECONCILIATION_REQUIRED,
                last_error="network interruption: reconciliation required",
            )
            print(
                f"[{plan.symbol}] network error during place_order — "
                "RECONCILIATION_REQUIRED; no auto-resubmit"
            )
            self.journal.write(
                "error",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=False,
                reason=f"network_{type(exc).__name__}",
                details=claimed.client_order_id,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False
        except Exception as exc:  # noqa: BLE001
            # Ambiguous: request may or may not have reached Bybit.
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.UNKNOWN,
                last_error=f"exception:{type(exc).__name__}",
                submission_attempted=True,
            )
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.RECONCILIATION_REQUIRED,
                last_error="exception during submit: reconciliation required",
            )
            print(
                f"[{plan.symbol}] place_order exception {type(exc).__name__} — "
                "RECONCILIATION_REQUIRED; no auto-resubmit"
            )
            self.journal.write(
                "error",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=False,
                reason=f"submit_exception_{type(exc).__name__}",
                details=claimed.client_order_id,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False

        if not isinstance(response, dict):
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.UNKNOWN,
                last_error="malformed place_order response",
                submission_attempted=True,
            )
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.RECONCILIATION_REQUIRED,
                last_error="malformed response: reconciliation required",
            )
            self.journal.write(
                "error",
                symbol=plan.symbol,
                category=self.settings.category,
                dry_run=False,
                reason="malformed_place_order_response",
                details=claimed.client_order_id,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False

        ret = response.get("retCode")
        if ret != 0:
            msg = str(response.get("retMsg") or "order rejected")
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.REJECTED,
                last_error=f"retCode={ret}:{msg}",
                submission_attempted=True,
            )
            print(f"[{plan.symbol}] order rejected:", msg)
            self.journal.write(
                "error",
                symbol=plan.symbol,
                category=self.settings.category,
                side=plan.side,
                qty=plan.qty,
                dry_run=False,
                reason=msg,
                details=claimed.client_order_id,
                equity="" if equity is None else f"{equity:.8f}",
            )
            return False

        result = response.get("result")
        if not isinstance(result, dict):
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.UNKNOWN,
                last_error="ack missing result object",
                submission_attempted=True,
            )
            self.store.transition(
                claimed.intent_id,
                OrderIntentState.RECONCILIATION_REQUIRED,
                last_error="ack malformed: reconciliation required",
            )
            return False

        order_id = str(result.get("orderId") or "")
        # Acknowledgement != fill.
        self.store.transition(
            claimed.intent_id,
            OrderIntentState.ACCEPTED,
            exchange_order_id=order_id,
            last_error="",
            submission_attempted=True,
        )
        print(
            f"[{plan.symbol}] ORDER ACCEPTED (not proven filled) {summary} "
            f"id={order_id} link={claimed.client_order_id}"
        )
        self.journal.write(
            "order",
            symbol=plan.symbol,
            category=self.settings.category,
            side=plan.side,
            qty=plan.qty,
            dry_run=False,
            reason=plan.reason,
            order_id=order_id,
            equity="" if equity is None else f"{equity:.8f}",
            details=f"{summary}; state=ACCEPTED; link={claimed.client_order_id}",
        )
        return True
