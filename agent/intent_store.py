"""Postgres persistence for order intents and execution evidence."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from agent.order_intent import (
    BLOCKING_EXPOSURE_STATES,
    NEEDS_RECONCILE_STATES,
    UNRESOLVED_STATES,
    OrderIntent,
    OrderIntentState,
    assert_transition,
    merge_reconcile_state,
    utc_now_iso,
)
from apps.api.app.persistence.ledger_models import OrderExecutionRow, OrderIntentRow
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
)


class IntentStoreError(RuntimeError):
    """Durable store failure — callers must fail closed for new exposure."""


@dataclass(frozen=True)
class ExecutionRow:
    exec_id: str
    order_id: str = ""
    order_link_id: str = ""
    exec_qty: str = "0"
    exec_price: str = "0"
    exec_fee: str = ""
    fee_currency: str = ""
    exec_time_ms: str = ""
    is_maker: bool | None = None
    leaves_qty: str = ""
    category: str = ""


class IntentStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._owner = resolve_sot_owner_user_id()
        self._engine = create_agent_engine(db_path)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()

    def _row_to_intent(self, row: OrderIntentRow) -> OrderIntent:
        return OrderIntent(
            intent_id=row.intent_id,
            client_order_id=row.client_order_id,
            env_scope=row.env_scope,
            account_fp=row.account_fp,
            symbol=row.symbol,
            category=row.category,
            side=row.side,
            qty=row.qty,
            reduce_only=bool(row.reduce_only),
            order_type=row.order_type,
            time_in_force=row.time_in_force,
            take_profit=row.take_profit,
            stop_loss=row.stop_loss,
            correlation_id=row.correlation_id,
            risk_auth_ref=row.risk_auth_ref,
            state=OrderIntentState(row.state),
            created_at=row.created_at,
            expires_at=row.expires_at,
            dry_run=bool(row.dry_run),
            exchange_order_id=row.exchange_order_id or "",
            last_error=row.last_error or "",
            filled_qty=row.filled_qty or "",
            remaining_qty=row.remaining_qty or "",
            avg_exec_price=row.avg_exec_price or "",
            cum_fee=row.cum_fee or "",
            evidence_status=row.evidence_status or "",
            submission_attempted=bool(row.submission_attempted),
            updated_at=row.updated_at or "",
        )

    def get_by_client_order_id(
        self, env_scope: str, account_fp: str, client_order_id: str
    ) -> OrderIntent | None:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.env_scope == env_scope,
                        OrderIntentRow.account_fp == account_fp,
                        OrderIntentRow.client_order_id == client_order_id,
                    )
                )
                return self._row_to_intent(row) if row else None
            finally:
                session.close()

    def get_by_intent_id(self, intent_id: str) -> OrderIntent | None:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                return self._row_to_intent(row) if row else None
            finally:
                session.close()

    def insert_created(self, intent: OrderIntent) -> tuple[bool, OrderIntent]:
        if intent.state is not OrderIntentState.CREATED:
            raise ValueError("insert_created requires CREATED state")
        with self._lock:
            session = self._Session()
            try:
                session.add(
                    OrderIntentRow(
                        intent_id=intent.intent_id,
                        owner_user_id=self._owner,
                        client_order_id=intent.client_order_id,
                        env_scope=intent.env_scope,
                        account_fp=intent.account_fp,
                        symbol=intent.symbol,
                        category=intent.category,
                        side=intent.side,
                        qty=intent.qty,
                        reduce_only=intent.reduce_only,
                        order_type=intent.order_type,
                        time_in_force=intent.time_in_force,
                        take_profit=intent.take_profit,
                        stop_loss=intent.stop_loss,
                        correlation_id=intent.correlation_id,
                        risk_auth_ref=intent.risk_auth_ref,
                        state=intent.state.value,
                        created_at=intent.created_at,
                        expires_at=intent.expires_at,
                        dry_run=intent.dry_run,
                        exchange_order_id=intent.exchange_order_id,
                        last_error=intent.last_error,
                        filled_qty=intent.filled_qty,
                        remaining_qty=intent.remaining_qty,
                        avg_exec_price=intent.avg_exec_price,
                        cum_fee=intent.cum_fee,
                        evidence_status=intent.evidence_status,
                        submission_attempted=intent.submission_attempted,
                        updated_at=utc_now_iso(),
                    )
                )
                session.commit()
                return True, intent
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.env_scope == intent.env_scope,
                        OrderIntentRow.account_fp == intent.account_fp,
                        OrderIntentRow.client_order_id == intent.client_order_id,
                    )
                )
                if existing is None:
                    raise IntentStoreError("unique conflict without existing row")
                return False, self._row_to_intent(existing)
            except Exception as exc:
                session.rollback()
                raise IntentStoreError(str(exc)) from exc
            finally:
                session.close()

    def transition(
        self,
        intent_id: str,
        new_state: OrderIntentState,
        *,
        exchange_order_id: str | None = None,
        last_error: str | None = None,
        filled_qty: str | None = None,
        remaining_qty: str | None = None,
        avg_exec_price: str | None = None,
        cum_fee: str | None = None,
        evidence_status: str | None = None,
        submission_attempted: bool | None = None,
    ) -> OrderIntent:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                if row is None:
                    raise KeyError(f"intent not found: {intent_id}")
                current = OrderIntentState(row.state)
                if current in {
                    OrderIntentState.FILLED,
                    OrderIntentState.REJECTED,
                    OrderIntentState.CANCELED,
                }:
                    if new_state is not current:
                        new_state = current
                    else:
                        assert_transition(current, new_state)
                else:
                    assert_transition(current, new_state)
                values: dict[str, object] = {
                    "state": new_state.value,
                    "updated_at": utc_now_iso(),
                }
                if exchange_order_id is not None:
                    values["exchange_order_id"] = exchange_order_id
                if last_error is not None:
                    values["last_error"] = last_error
                if filled_qty is not None:
                    values["filled_qty"] = filled_qty
                if remaining_qty is not None:
                    values["remaining_qty"] = remaining_qty
                if avg_exec_price is not None:
                    values["avg_exec_price"] = avg_exec_price
                if cum_fee is not None:
                    values["cum_fee"] = cum_fee
                if evidence_status is not None:
                    values["evidence_status"] = evidence_status
                if submission_attempted is not None:
                    values["submission_attempted"] = submission_attempted
                session.execute(
                    update(OrderIntentRow)
                    .where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                    .values(**values)
                )
                session.commit()
                refreshed = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                assert refreshed is not None
                return self._row_to_intent(refreshed)
            except (KeyError, ValueError):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                raise IntentStoreError(str(exc)) from exc
            finally:
                session.close()

    def apply_reconcile_update(
        self,
        intent_id: str,
        *,
        proposed_state: OrderIntentState,
        executions: list[ExecutionRow],
        exchange_order_id: str | None = None,
        filled_qty: str | None = None,
        remaining_qty: str | None = None,
        avg_exec_price: str | None = None,
        cum_fee: str | None = None,
        evidence_status: str | None = None,
        last_error: str | None = None,
        conflict: bool = False,
    ) -> tuple[OrderIntent, int]:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                if row is None:
                    raise KeyError(f"intent not found: {intent_id}")
                current = OrderIntentState(row.state)
                env_scope = row.env_scope
                account_fp = row.account_fp
                inserted = 0
                now = utc_now_iso()
                seen_exec: set[str] = set()
                for ex in executions:
                    if not ex.exec_id or ex.exec_id in seen_exec:
                        continue
                    seen_exec.add(ex.exec_id)
                    exists = session.scalar(
                        select(OrderExecutionRow).where(
                            OrderExecutionRow.owner_user_id == self._owner,
                            OrderExecutionRow.env_scope == env_scope,
                            OrderExecutionRow.account_fp == account_fp,
                            OrderExecutionRow.exec_id == ex.exec_id,
                        )
                    )
                    if exists is not None:
                        continue
                    session.add(
                        OrderExecutionRow(
                            owner_user_id=self._owner,
                            env_scope=env_scope,
                            account_fp=account_fp,
                            intent_id=intent_id,
                            exec_id=ex.exec_id,
                            order_id=ex.order_id,
                            order_link_id=ex.order_link_id,
                            exec_qty=ex.exec_qty,
                            exec_price=ex.exec_price,
                            exec_fee=ex.exec_fee,
                            fee_currency=ex.fee_currency,
                            exec_time_ms=ex.exec_time_ms,
                            is_maker=ex.is_maker,
                            leaves_qty=ex.leaves_qty,
                            category=ex.category,
                            created_at=now,
                        )
                    )
                    inserted += 1
                if conflict:
                    target = merge_reconcile_state(current, OrderIntentState.UNKNOWN)
                    if target is current and current not in {
                        OrderIntentState.UNKNOWN,
                        OrderIntentState.RECONCILIATION_REQUIRED,
                    }:
                        if current not in {
                            OrderIntentState.FILLED,
                            OrderIntentState.REJECTED,
                            OrderIntentState.CANCELED,
                        }:
                            target = OrderIntentState.UNKNOWN
                else:
                    target = merge_reconcile_state(current, proposed_state)
                    if target is not current:
                        assert_transition(current, target)
                session.execute(
                    update(OrderIntentRow)
                    .where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                    .values(
                        state=target.value,
                        exchange_order_id=exchange_order_id or row.exchange_order_id,
                        last_error=last_error or row.last_error,
                        filled_qty=filled_qty or row.filled_qty,
                        remaining_qty=remaining_qty or row.remaining_qty,
                        avg_exec_price=avg_exec_price or row.avg_exec_price,
                        cum_fee=cum_fee or row.cum_fee,
                        evidence_status=evidence_status or row.evidence_status,
                        updated_at=now,
                    )
                )
                session.commit()
                refreshed = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                assert refreshed is not None
                return self._row_to_intent(refreshed), inserted
            except (KeyError, ValueError):
                session.rollback()
                raise
            except Exception as exc:
                session.rollback()
                raise IntentStoreError(str(exc)) from exc
            finally:
                session.close()

    def list_executions(self, intent_id: str) -> list[ExecutionRow]:
        with self._lock:
            session = self._Session()
            try:
                rows = session.scalars(
                    select(OrderExecutionRow)
                    .where(
                        OrderExecutionRow.owner_user_id == self._owner,
                        OrderExecutionRow.intent_id == intent_id,
                    )
                    .order_by(OrderExecutionRow.exec_time_ms.asc(), OrderExecutionRow.exec_id.asc())
                ).all()
                return [
                    ExecutionRow(
                        exec_id=r.exec_id,
                        order_id=r.order_id or "",
                        order_link_id=r.order_link_id or "",
                        exec_qty=r.exec_qty,
                        exec_price=r.exec_price,
                        exec_fee=r.exec_fee or "",
                        fee_currency=r.fee_currency or "",
                        exec_time_ms=r.exec_time_ms or "",
                        is_maker=r.is_maker,
                        leaves_qty=r.leaves_qty or "",
                        category=r.category or "",
                    )
                    for r in rows
                ]
            finally:
                session.close()

    def mark_restart_recovery(
        self, env_scope: str, account_fp: str
    ) -> list[OrderIntent]:
        recovered: list[OrderIntent] = []
        with self._lock:
            session = self._Session()
            try:
                rows = session.scalars(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.env_scope == env_scope,
                        OrderIntentRow.account_fp == account_fp,
                        OrderIntentRow.state.in_(
                            [
                                OrderIntentState.SUBMISSION_PENDING.value,
                                OrderIntentState.UNKNOWN.value,
                            ]
                        ),
                        OrderIntentRow.dry_run.is_(False),
                    )
                ).all()
                for row in rows:
                    current = OrderIntentState(row.state)
                    target = OrderIntentState.RECONCILIATION_REQUIRED
                    assert_transition(current, target)
                    row.state = target.value
                    row.last_error = "restart recovery: unresolved submission"
                    row.updated_at = utc_now_iso()
                    recovered.append(self._row_to_intent(row))
                session.commit()
                return recovered
            except Exception as exc:
                session.rollback()
                raise IntentStoreError(str(exc)) from exc
            finally:
                session.close()

    def list_unresolved(
        self, env_scope: str, account_fp: str, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        return self._list_by_states(
            env_scope, account_fp, UNRESOLVED_STATES, symbol=symbol
        )

    def list_blocking_exposure(
        self, env_scope: str, account_fp: str, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        return self._list_by_states(
            env_scope, account_fp, BLOCKING_EXPOSURE_STATES, symbol=symbol
        )

    def list_needs_reconcile(
        self, env_scope: str, account_fp: str, *, symbol: str | None = None
    ) -> list[OrderIntent]:
        return self._list_by_states(
            env_scope, account_fp, NEEDS_RECONCILE_STATES, symbol=symbol
        )

    def list_recent_for_observation(
        self,
        env_scope: str,
        account_fp: str,
        *,
        limit: int = 200,
    ) -> list[OrderIntent]:
        limit = max(1, min(int(limit), 500))
        with self._lock:
            session = self._Session()
            try:
                rows = session.scalars(
                    select(OrderIntentRow)
                    .where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.env_scope == env_scope,
                        OrderIntentRow.account_fp == account_fp,
                    )
                    .order_by(
                        OrderIntentRow.updated_at.desc(), OrderIntentRow.created_at.desc()
                    )
                    .limit(limit)
                ).all()
                return [self._row_to_intent(r) for r in rows]
            finally:
                session.close()

    def _list_by_states(
        self,
        env_scope: str,
        account_fp: str,
        states: frozenset[OrderIntentState],
        *,
        symbol: str | None = None,
    ) -> list[OrderIntent]:
        state_vals = [s.value for s in states]
        with self._lock:
            session = self._Session()
            try:
                stmt = select(OrderIntentRow).where(
                    OrderIntentRow.owner_user_id == self._owner,
                    OrderIntentRow.env_scope == env_scope,
                    OrderIntentRow.account_fp == account_fp,
                    OrderIntentRow.dry_run.is_(False),
                    OrderIntentRow.state.in_(state_vals),
                )
                if symbol:
                    stmt = stmt.where(OrderIntentRow.symbol == symbol)
                rows = session.scalars(stmt).all()
                return [self._row_to_intent(r) for r in rows]
            finally:
                session.close()

    def try_claim_for_submission(self, intent_id: str) -> OrderIntent | None:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                if row is None or row.state != OrderIntentState.CREATED.value or row.dry_run:
                    return None
                result = session.execute(
                    update(OrderIntentRow)
                    .where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                        OrderIntentRow.state == OrderIntentState.CREATED.value,
                        OrderIntentRow.dry_run.is_(False),
                    )
                    .values(
                        state=OrderIntentState.SUBMISSION_PENDING.value,
                        submission_attempted=True,
                        updated_at=utc_now_iso(),
                    )
                )
                if result.rowcount != 1:
                    session.rollback()
                    return None
                session.commit()
                refreshed = session.scalar(
                    select(OrderIntentRow).where(
                        OrderIntentRow.owner_user_id == self._owner,
                        OrderIntentRow.intent_id == intent_id,
                    )
                )
                return self._row_to_intent(refreshed) if refreshed else None
            except Exception as exc:
                session.rollback()
                raise IntentStoreError(str(exc)) from exc
            finally:
                session.close()
