"""Risk manager with durable, fail-closed account risk state (Phase 1C)."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path

from pybit.unified_trading import HTTP

from agent.config import AgentSettings, live_orders_blocked
from agent.market_data import PositionSnapshot, PositionStatus
from agent.order_ids import account_fingerprint, env_scope_id
from agent.risk_modes import AccountRiskMode, allows_new_exposure, allows_reduce_only
from agent.risk_store import (
    AccountRiskRecord,
    RiskStore,
    RiskStoreError,
    utc_now_iso,
    utc_today,
)
from agent.strategies.base import Signal, SignalAction
from bot.config import API_KEY, USE_DEMO, USE_TESTNET
from bot.market import get_instrument, normalize_qty, split_symbol
from bot.utils import format_decimal

# Explicit operator acknowledgement required for recovery (not used by strategies).
OPERATOR_RECOVERY_ACK = "I_ACKNOWLEDGE_ACCOUNT_VERIFIED"


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    side: str  # Buy / Sell
    qty: str
    reduce_only: bool
    take_profit: str | None = None
    stop_loss: str | None = None
    reason: str = ""
    correlation_id: str = ""
    risk_auth_ref: str = ""


@dataclass
class RiskView:
    """In-memory projection for runner compatibility / status display."""

    mode: AccountRiskMode = AccountRiskMode.RECOVERY_REQUIRED
    halted: bool = True
    halt_reason: str = "risk state not loaded"
    start_equity: float | None = None
    latest_equity: float | None = None
    equity_confirmed: bool = False
    recovery_required: bool = True
    daily_loss_pct_current: float | None = None
    risk_date: str = ""


class RiskManager:
    """
    Durable risk controls.

    Daily loss uses UNIFIED wallet ``totalEquity`` (mark-to-market; includes
    unrealized). ``AGENT_RISK_PCT`` remains a *sizing budget*, not the daily
    loss limit (``AGENT_DAILY_LOSS_PCT``).
    """

    def __init__(
        self,
        settings: AgentSettings,
        *,
        store: RiskStore | None = None,
        db_path: str | Path | None = None,
        unresolved_intent_checker: Callable[[], list] | None = None,
    ) -> None:
        self.settings = settings
        self.env_scope = env_scope_id(use_testnet=USE_TESTNET, use_demo=USE_DEMO)
        self.account_fp = account_fingerprint(API_KEY)
        self._unresolved_intent_checker = unresolved_intent_checker
        self._fail_closed_reason = ""
        try:
            self.store = store or RiskStore(db_path=db_path)
            self.record = self._bootstrap_today(equity=None)
            self._fail_closed = False
        except RiskStoreError as exc:
            self.store = store  # may be None
            self.record = None
            self._fail_closed = True
            self._fail_closed_reason = str(exc)

    @property
    def state(self) -> RiskView:
        """Backward-compatible view used by runner halt checks."""
        if self._fail_closed or self.record is None:
            return RiskView(
                mode=AccountRiskMode.RECOVERY_REQUIRED,
                halted=True,
                halt_reason=self._fail_closed_reason or "risk store unavailable",
                recovery_required=True,
            )
        r = self.record
        halted = r.mode is AccountRiskMode.HALTED or r.emergency_halt
        return RiskView(
            mode=r.mode,
            halted=halted,
            halt_reason=r.halt_reason,
            start_equity=r.start_equity,
            latest_equity=r.latest_equity,
            equity_confirmed=r.equity_confirmed,
            recovery_required=r.recovery_required
            or r.mode is AccountRiskMode.RECOVERY_REQUIRED,
            daily_loss_pct_current=r.daily_loss_pct_current,
            risk_date=r.risk_date,
        )

    def _bootstrap_today(self, equity: float | None) -> AccountRiskRecord:
        today = utc_today().isoformat()
        existing = self.store.get(self.env_scope, self.account_fp, today)
        if existing is not None:
            # Never overwrite an existing baseline on restart.
            return existing

        prior = self.store.latest_emergency(self.env_scope, self.account_fp)
        emergency = bool(prior and prior.emergency_halt)
        if equity is None or equity <= 0:
            mode = (
                AccountRiskMode.HALTED
                if emergency
                else AccountRiskMode.RECOVERY_REQUIRED
            )
            record = AccountRiskRecord(
                env_scope=self.env_scope,
                account_fp=self.account_fp,
                risk_date=today,
                mode=mode,
                start_equity=None,
                latest_equity=None,
                equity_confirmed=False,
                realized_pnl=None,
                unrealized_pnl=None,
                daily_loss_pct_threshold=float(self.settings.daily_loss_pct),
                daily_loss_pct_current=None,
                emergency_halt=emergency,
                halt_reason=(
                    prior.halt_reason
                    if emergency and prior
                    else "awaiting confirmed equity"
                ),
                recovery_required=True,
                version=1,
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
            return self.store.insert_new_day(record)

        mode = AccountRiskMode.HALTED if emergency else AccountRiskMode.NORMAL
        record = AccountRiskRecord(
            env_scope=self.env_scope,
            account_fp=self.account_fp,
            risk_date=today,
            mode=mode,
            start_equity=equity,
            latest_equity=equity,
            equity_confirmed=True,
            realized_pnl=None,
            unrealized_pnl=None,
            daily_loss_pct_threshold=float(self.settings.daily_loss_pct),
            daily_loss_pct_current=0.0,
            emergency_halt=emergency,
            halt_reason=(prior.halt_reason if emergency and prior else ""),
            recovery_required=emergency,
            version=1,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        )
        return self.store.insert_new_day(record)

    def _ensure_today(self) -> AccountRiskRecord:
        if self._fail_closed or self.store is None:
            raise RiskStoreError(self._fail_closed_reason or "risk store unavailable")
        today = utc_today().isoformat()
        if self.record is None or self.record.risk_date != today:
            # UTC midnight rollover: new row; carry emergency halt; do not clear it.
            equity = (
                self.record.latest_equity
                if self.record and self.record.equity_confirmed
                else None
            )
            self.record = self._bootstrap_today(equity=equity)
        return self.record

    def _persist(self, updated: AccountRiskRecord) -> AccountRiskRecord:
        assert self.record is not None
        self.record = self.store.update_cas(self.record, updated)
        return self.record

    def update_equity(
        self,
        equity: float | None,
        *,
        unrealized_pnl: float | None = None,
        realized_pnl: float | None = None,
    ) -> RiskView:
        try:
            record = self._ensure_today()
        except RiskStoreError as exc:
            self._fail_closed = True
            self._fail_closed_reason = str(exc)
            return self.state

        if equity is None or equity <= 0:
            # Unknown/stale equity: fail closed — never authorize new exposure.
            new_mode = record.mode
            if record.mode is AccountRiskMode.NORMAL:
                new_mode = AccountRiskMode.RECOVERY_REQUIRED
            elif record.mode is AccountRiskMode.REDUCE_ONLY:
                new_mode = AccountRiskMode.RECOVERY_REQUIRED
            updated = replace(
                record,
                mode=new_mode,
                equity_confirmed=False,
                recovery_required=True,
                halt_reason=record.halt_reason or "equity read failed or invalid",
                updated_at=utc_now_iso(),
            )
            try:
                self._persist(updated)
            except RiskStoreError as exc:
                self._fail_closed = True
                self._fail_closed_reason = str(exc)
            return self.state

        # Confirmed equity path
        start = record.start_equity
        if start is None:
            # First confirmed equity for the day — set baseline once.
            start = equity

        loss_pct = 0.0
        if start > 0:
            loss_pct = ((start - equity) / start) * 100.0

        mode = record.mode
        emergency = record.emergency_halt
        halt_reason = record.halt_reason
        recovery_required = record.recovery_required

        if emergency or mode is AccountRiskMode.HALTED:
            mode = AccountRiskMode.HALTED
            emergency = True
        elif loss_pct >= record.daily_loss_pct_threshold:
            mode = AccountRiskMode.HALTED
            emergency = True
            halt_reason = (
                f"Daily loss limit hit ({loss_pct:.2f}% >= "
                f"{record.daily_loss_pct_threshold}%)"
            )
            recovery_required = True
        elif mode is AccountRiskMode.RECOVERY_REQUIRED and not emergency:
            # Only auto-clear the *initial* "awaiting first equity" bootstrap.
            # Any later RECOVERY_REQUIRED (failed reads, incidents) needs operator recovery.
            if (
                record.start_equity is None
                and record.halt_reason == "awaiting confirmed equity"
            ):
                mode = AccountRiskMode.NORMAL
                recovery_required = False
                halt_reason = ""
            # else: stay RECOVERY_REQUIRED until attempt_operator_recovery()
        elif mode is AccountRiskMode.NORMAL:
            pass

        updated = replace(
            record,
            mode=mode,
            start_equity=start,
            latest_equity=equity,
            equity_confirmed=True,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            daily_loss_pct_current=loss_pct,
            emergency_halt=emergency,
            halt_reason=halt_reason,
            recovery_required=recovery_required or emergency,
            updated_at=utc_now_iso(),
        )
        try:
            self._persist(updated)
        except RiskStoreError as exc:
            self._fail_closed = True
            self._fail_closed_reason = str(exc)
        return self.state

    def _unresolved_intents_exist(self) -> bool:
        if self._unresolved_intent_checker is None:
            return False
        try:
            items = self._unresolved_intent_checker()
            return bool(items)
        except Exception:  # noqa: BLE001 — fail closed
            return True

    def authorize_new_exposure(self) -> str | None:
        """Return block reason, or None if new exposure is allowed."""
        if self._fail_closed or self.record is None:
            return self._fail_closed_reason or "risk store unavailable"
        try:
            record = self._ensure_today()
        except RiskStoreError as exc:
            return str(exc)
        if not record.equity_confirmed:
            return "equity not confirmed"
        if not allows_new_exposure(record.mode):
            return f"risk mode {record.mode.value} blocks new exposure"
        if record.recovery_required or record.emergency_halt:
            return "recovery required before new exposure"
        if self._unresolved_intents_exist():
            return "unresolved order intent blocks risk authorization"
        return None

    def authorize_reduce_only(self) -> str | None:
        if self._fail_closed or self.record is None:
            return self._fail_closed_reason or "risk store unavailable"
        try:
            record = self._ensure_today()
        except RiskStoreError as exc:
            return str(exc)
        if not allows_reduce_only(record.mode):
            return f"risk mode {record.mode.value} blocks reduce-only"
        return None

    def attempt_operator_recovery(
        self,
        *,
        authorization_token: str,
        acknowledge: str,
        verified_equity: float | None,
    ) -> tuple[bool, str]:
        """
        Manual operator recovery only. Strategies/LLMs must not call this.

        Requires:
        - acknowledge == OPERATOR_RECOVERY_ACK
        - authorization_token matches non-empty AGENT_RISK_RECOVERY_TOKEN
        - verified_equity confirmed
        - no unresolved Phase 1B intents
        """
        if acknowledge != OPERATOR_RECOVERY_ACK:
            return False, "missing operator acknowledgement"
        expected = os.getenv("AGENT_RISK_RECOVERY_TOKEN", "").strip()
        if not expected or authorization_token != expected:
            return False, "unauthorized recovery token"
        if verified_equity is None or verified_equity <= 0:
            return False, "verified equity required"
        if self._unresolved_intents_exist():
            return False, "unresolved order intents must be cleared first"
        if self._fail_closed or self.store is None or self.record is None:
            return False, "risk store unavailable"

        try:
            record = self._ensure_today()
            updated = replace(
                record,
                mode=AccountRiskMode.NORMAL,
                start_equity=record.start_equity or verified_equity,
                latest_equity=verified_equity,
                equity_confirmed=True,
                emergency_halt=False,
                halt_reason="",
                recovery_required=False,
                daily_loss_pct_current=0.0
                if not record.start_equity
                else ((record.start_equity - verified_equity) / record.start_equity)
                * 100.0,
                updated_at=utc_now_iso(),
            )
            # If still beyond daily loss after recovery equity, keep halted.
            start = updated.start_equity or verified_equity
            if start > 0:
                loss = ((start - verified_equity) / start) * 100.0
                updated = replace(updated, daily_loss_pct_current=loss)
                if loss >= record.daily_loss_pct_threshold:
                    return False, "daily loss still breached; cannot clear halt"
            self._persist(updated)
            self._fail_closed = False
            self._fail_closed_reason = ""
            return True, "recovered_to_NORMAL"
        except RiskStoreError as exc:
            return False, str(exc)

    def open_position_count(self, positions: dict[str, PositionSnapshot]) -> int:
        """Count confirmed opens plus UNKNOWN (UNKNOWN may already be exposure)."""
        return sum(
            1
            for snap in positions.values()
            if snap.status in {PositionStatus.OPEN, PositionStatus.UNKNOWN}
        )

    def plan_trade(
        self,
        session: HTTP,
        symbol: str,
        signal: Signal,
        snapshot: PositionSnapshot,
        equity: float | None,
        open_count: int,
    ) -> TradePlan | None:
        block = live_orders_blocked(self.settings)
        if signal.action == SignalAction.HOLD:
            return None

        # Fail-closed: never open when position state is ambiguous.
        if snapshot.status is PositionStatus.UNKNOWN:
            return None

        category = self.settings.category
        price = Decimal(str(signal.price))

        # Close / reverse logic — only with confirmed OPEN
        if snapshot.status is PositionStatus.OPEN:
            reduce_block = self.authorize_reduce_only()
            if reduce_block:
                return None
            position = snapshot.position or {}
            pos_side = position.get("side")
            if signal.action == SignalAction.SELL and pos_side == "Buy":
                qty = normalize_qty(
                    session,
                    category,
                    symbol,
                    Decimal(str(position["size"])),
                )
                if not qty:
                    return None
                return TradePlan(
                    symbol=symbol,
                    side="Sell",
                    qty=qty,
                    reduce_only=(category == "linear"),
                    reason=f"Close long: {signal.reason}",
                    risk_auth_ref=f"reduce:{self.state.mode.value}",
                )
            if signal.action == SignalAction.BUY and pos_side == "Sell":
                qty = normalize_qty(
                    session,
                    category,
                    symbol,
                    Decimal(str(position["size"])),
                )
                if not qty:
                    return None
                return TradePlan(
                    symbol=symbol,
                    side="Buy",
                    qty=qty,
                    reduce_only=(category == "linear"),
                    reason=f"Close short: {signal.reason}",
                    risk_auth_ref=f"reduce:{self.state.mode.value}",
                )
            # Same-direction signal while in position → hold
            return None

        # New exposure path
        exposure_block = self.authorize_new_exposure()
        if exposure_block:
            return None

        if open_count >= self.settings.max_open_positions:
            return None

        if category == "spot" and signal.action == SignalAction.SELL:
            return None

        if equity is None or equity <= 0 or price <= 0:
            return None

        side = "Buy" if signal.action == SignalAction.BUY else "Sell"
        # AGENT_RISK_PCT = sizing / margin budget — NOT the daily loss limit.
        notional = Decimal(str(equity)) * (
            Decimal(str(self.settings.risk_pct_equity)) / Decimal("100")
        )
        if category == "linear":
            notional = notional * Decimal(self.settings.leverage)

        raw_qty = notional / price
        qty = normalize_qty(session, category, symbol, raw_qty)
        if not qty:
            instrument = get_instrument(session, category, symbol)
            min_qty = (instrument or {}).get("lotSizeFilter", {}).get("minOrderQty")
            print(
                f"[{symbol}] size below exchange minimum "
                f"(wanted ~{format_decimal(raw_qty)}, min={min_qty}). Skip."
            )
            return None

        instrument = get_instrument(session, category, symbol)
        if instrument:
            min_qty = Decimal(
                (instrument.get("lotSizeFilter") or {}).get("minOrderQty") or "0"
            )
            min_cost = min_qty * price
            if category == "linear":
                min_margin = min_cost / Decimal(self.settings.leverage)
                if Decimal(str(equity)) < min_margin:
                    print(
                        f"[{symbol}] equity too small for min contract "
                        f"(need margin ≈ {format_decimal(min_margin)}). Skip."
                    )
                    return None
            else:
                _, quote = split_symbol(symbol)
                if Decimal(str(equity)) < min_cost:
                    print(
                        f"[{symbol}] equity too small for min spot qty "
                        f"(need ≈ {format_decimal(min_cost)} {quote}). Skip."
                    )
                    return None

        tp = sl = None
        if category == "linear":
            if side == "Buy":
                tp_px = price * (
                    Decimal("1")
                    + Decimal(str(self.settings.take_profit_pct)) / Decimal("100")
                )
                sl_px = price * (
                    Decimal("1")
                    - Decimal(str(self.settings.stop_loss_pct)) / Decimal("100")
                )
            else:
                tp_px = price * (
                    Decimal("1")
                    - Decimal(str(self.settings.take_profit_pct)) / Decimal("100")
                )
                sl_px = price * (
                    Decimal("1")
                    + Decimal(str(self.settings.stop_loss_pct)) / Decimal("100")
                )
            tick = Decimal(
                ((instrument or {}).get("priceFilter") or {}).get("tickSize") or "0.01"
            )
            from bot.utils import floor_to_step

            tp = format_decimal(floor_to_step(tp_px, tick))
            sl = format_decimal(floor_to_step(sl_px, tick))

        _ = block  # enforced at execute time
        return TradePlan(
            symbol=symbol,
            side=side,
            qty=qty,
            reduce_only=False,
            take_profit=tp,
            stop_loss=sl,
            reason=signal.reason,
            risk_auth_ref=f"exposure:{self.state.mode.value}",
        )
