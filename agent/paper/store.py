"""Postgres / SQLAlchemy persistence for local paper broker (Supabase SoT)."""

from __future__ import annotations

import json
import threading
import uuid
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from agent.paper.config import PaperBrokerConfig, d
from agent.paper.models import (
    OrderSide,
    OrderStatus,
    PaperFill,
    PaperOrder,
    PaperPosition,
    PaperSession,
    PositionStatus,
    SessionStatus,
)
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.paper_models import (
    PaperAccountEventRow,
    PaperCandleCursorRow,
    PaperEquitySnapshotRow,
    PaperFillRow,
    PaperMetaRow,
    PaperOrderRow,
    PaperPositionRow,
    PaperProcessedEventRow,
    PaperRiskStateRow,
    PaperSessionRow,
)
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
)

SCHEMA_VERSION = 2


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class PaperStore:
    """Thread-safe paper broker store backed by SQLAlchemy (Postgres SoT or offline SQLite)."""

    def __init__(self, db_path: str | Path | None = None, *, isolated_sqlite: bool = False) -> None:
        self._isolated_sqlite = isolated_sqlite
        self._owner = resolve_sot_owner_user_id(required=False if isolated_sqlite else None)
        self._engine = create_agent_engine(db_path, isolated_sqlite=isolated_sqlite)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()
        self._init_schema()

    def _session(self) -> Session:
        return self._Session()

    def _init_schema(self) -> None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperMetaRow).where(
                        PaperMetaRow.owner_user_id == self._owner,
                        PaperMetaRow.key == "schema_version",
                    )
                )
                if row is None:
                    session.add(
                        PaperMetaRow(
                            owner_user_id=self._owner,
                            key="schema_version",
                            value=str(SCHEMA_VERSION),
                        )
                    )
                    session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise
            finally:
                session.close()

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        with self._lock:
            session = self._session()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

    def create_session(
        self,
        *,
        config: PaperBrokerConfig,
        now_ms: int,
        session_id: str | None = None,
    ) -> PaperSession:
        sid = session_id or new_id("ps")
        sess = PaperSession(
            session_id=sid,
            initial_balance=config.initial_balance,
            available_balance=config.initial_balance,
            reserved_capital=Decimal("0"),
            realized_pnl=Decimal("0"),
            fees_paid=Decimal("0"),
            status=SessionStatus.ACTIVE,
            created_ms=now_ms,
            updated_ms=now_ms,
            config_json=json.dumps(config.to_dict()),
            currency=config.currency,
        )
        with self.transaction() as session:
            session.add(
                PaperSessionRow(
                    session_id=sid,
                    owner_user_id=self._owner,
                    initial_balance=str(sess.initial_balance),
                    available_balance=str(sess.available_balance),
                    reserved_capital=str(sess.reserved_capital),
                    realized_pnl=str(sess.realized_pnl),
                    fees_paid=str(sess.fees_paid),
                    status=sess.status.value,
                    created_ms=sess.created_ms,
                    updated_ms=sess.updated_ms,
                    config_json=sess.config_json,
                    currency=sess.currency,
                )
            )
            # Ensure parent row exists before FK child inserts in same TX.
            session.flush()
            self._append_event(
                session,
                session_id=sid,
                event_type="SESSION_CREATED",
                payload={"initial_balance": str(config.initial_balance)},
                created_ms=now_ms,
                idempotency_key=f"session_created:{sid}",
            )
        return sess

    def get_session(self, session_id: str) -> PaperSession | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperSessionRow).where(
                        PaperSessionRow.session_id == session_id,
                        PaperSessionRow.owner_user_id == self._owner,
                    )
                )
                return self._row_to_session(row) if row else None
            finally:
                session.close()

    def get_session_for_update(self, conn: Any, session_id: str) -> PaperSession | None:
        row = conn.scalar(
            select(PaperSessionRow).where(
                PaperSessionRow.session_id == session_id,
                PaperSessionRow.owner_user_id == self._owner,
            )
        )
        return self._row_to_session(row) if row else None

    def count_open_positions(self, conn: Any, session_id: str) -> int:
        return int(
            conn.scalar(
                select(func.count())
                .select_from(PaperPositionRow)
                .where(
                    PaperPositionRow.session_id == session_id,
                    PaperPositionRow.status == PositionStatus.OPEN.value,
                    PaperPositionRow.owner_user_id == self._owner,
                )
            )
            or 0
        )

    def risk_halted_in_txn(self, conn: Any, session_id: str) -> bool:
        row = conn.scalar(
            select(PaperRiskStateRow).where(
                PaperRiskStateRow.session_id == session_id,
                PaperRiskStateRow.owner_user_id == self._owner,
            )
        )
        return bool(row.halted) if row is not None else False

    def risk_halt_ms_in_txn(self, conn: Any, session_id: str) -> int | None:
        row = conn.scalar(
            select(PaperRiskStateRow).where(
                PaperRiskStateRow.session_id == session_id,
                PaperRiskStateRow.owner_user_id == self._owner,
            )
        )
        return int(row.halt_ms) if row is not None and row.halt_ms is not None else None

    def update_session_balances(
        self,
        conn: Any,
        *,
        session_id: str,
        available: Decimal,
        reserved: Decimal,
        realized_pnl: Decimal,
        fees_paid: Decimal,
        updated_ms: int,
    ) -> None:
        if available < 0:
            raise ValueError("available_balance cannot be negative")
        if reserved < 0:
            raise ValueError("reserved_capital cannot be negative")
        conn.execute(
            update(PaperSessionRow)
            .where(
                PaperSessionRow.session_id == session_id,
                PaperSessionRow.owner_user_id == self._owner,
            )
            .values(
                available_balance=str(available),
                reserved_capital=str(reserved),
                realized_pnl=str(realized_pnl),
                fees_paid=str(fees_paid),
                updated_ms=updated_ms,
            )
        )

    def insert_order(self, conn: Any, order: PaperOrder) -> None:
        conn.add(
            PaperOrderRow(
                order_id=order.order_id,
                owner_user_id=self._owner,
                session_id=order.session_id,
                source_signal_id=order.source_signal_id,
                symbol=order.symbol,
                category=order.category,
                side=order.side.value,
                quantity=str(order.quantity),
                intended_entry_price=str(order.intended_entry_price),
                status=order.status.value,
                created_ms=order.created_ms,
                filled_ms=order.filled_ms,
                fill_price=str(order.fill_price) if order.fill_price is not None else None,
                fee=str(order.fee),
                slippage=str(order.slippage),
                rejection_reason=order.rejection_reason,
                stop_loss=str(order.stop_loss) if order.stop_loss is not None else None,
                take_profit=str(order.take_profit) if order.take_profit is not None else None,
                signal_candle_start_ms=order.signal_candle_start_ms,
                simulated=order.simulated,
            )
        )

    def get_order(self, order_id: str) -> PaperOrder | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperOrderRow).where(
                        PaperOrderRow.order_id == order_id,
                        PaperOrderRow.owner_user_id == self._owner,
                    )
                )
                return self._row_to_order(row) if row else None
            finally:
                session.close()

    def get_order_by_signal(
        self, session_id: str, source_signal_id: str, side: str
    ) -> PaperOrder | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperOrderRow).where(
                        PaperOrderRow.session_id == session_id,
                        PaperOrderRow.source_signal_id == source_signal_id,
                        PaperOrderRow.side == side,
                        PaperOrderRow.owner_user_id == self._owner,
                    )
                )
                return self._row_to_order(row) if row else None
            finally:
                session.close()

    def list_pending_orders(self, session_id: str) -> list[PaperOrder]:
        with self._lock:
            session = self._session()
            try:
                rows = session.scalars(
                    select(PaperOrderRow)
                    .where(
                        PaperOrderRow.session_id == session_id,
                        PaperOrderRow.status == OrderStatus.PENDING.value,
                        PaperOrderRow.owner_user_id == self._owner,
                    )
                    .order_by(PaperOrderRow.created_ms.asc())
                ).all()
                return [self._row_to_order(r) for r in rows]
            finally:
                session.close()

    def update_order_filled(
        self,
        conn: Any,
        *,
        order_id: str,
        fill_price: Decimal,
        fee: Decimal,
        slippage: Decimal,
        filled_ms: int,
    ) -> None:
        result = conn.execute(
            update(PaperOrderRow)
            .where(
                PaperOrderRow.order_id == order_id,
                PaperOrderRow.status == OrderStatus.PENDING.value,
                PaperOrderRow.owner_user_id == self._owner,
            )
            .values(
                status=OrderStatus.FILLED.value,
                fill_price=str(fill_price),
                fee=str(fee),
                slippage=str(slippage),
                filled_ms=filled_ms,
            )
        )
        if result.rowcount == 0:
            raise RuntimeError(f"order {order_id} not pending for fill")

    def update_order_rejected(
        self,
        conn: Any,
        *,
        order_id: str,
        reason: str,
    ) -> None:
        conn.execute(
            update(PaperOrderRow)
            .where(
                PaperOrderRow.order_id == order_id,
                PaperOrderRow.status == OrderStatus.PENDING.value,
                PaperOrderRow.owner_user_id == self._owner,
            )
            .values(status=OrderStatus.REJECTED.value, rejection_reason=reason)
        )

    def insert_fill(self, conn: Any, fill: PaperFill) -> None:
        conn.add(
            PaperFillRow(
                fill_id=fill.fill_id,
                owner_user_id=self._owner,
                order_id=fill.order_id,
                session_id=fill.session_id,
                symbol=fill.symbol,
                side=fill.side.value,
                quantity=str(fill.quantity),
                price=str(fill.price),
                fee=str(fill.fee),
                slippage=str(fill.slippage),
                filled_ms=fill.filled_ms,
                candle_start_ms=fill.candle_start_ms,
                role=fill.role,
            )
        )

    def insert_position(self, conn: Any, pos: PaperPosition) -> None:
        conn.add(
            PaperPositionRow(
                position_id=pos.position_id,
                owner_user_id=self._owner,
                session_id=pos.session_id,
                symbol=pos.symbol,
                category=pos.category,
                status=pos.status.value,
                quantity=str(pos.quantity),
                entry_price=str(pos.entry_price),
                entry_fee=str(pos.entry_fee),
                entry_order_id=pos.entry_order_id,
                entry_signal_id=pos.entry_signal_id,
                stop_loss=str(pos.stop_loss) if pos.stop_loss is not None else None,
                take_profit=str(pos.take_profit) if pos.take_profit is not None else None,
                opened_ms=pos.opened_ms,
                closed_ms=pos.closed_ms,
                exit_price=str(pos.exit_price) if pos.exit_price is not None else None,
                exit_fee=str(pos.exit_fee),
                exit_order_id=pos.exit_order_id,
                exit_reason=pos.exit_reason,
                realized_pnl=str(pos.realized_pnl),
                mark_price=str(pos.mark_price) if pos.mark_price is not None else None,
                unrealized_pnl=str(pos.unrealized_pnl),
            )
        )

    def get_open_positions(self, session_id: str) -> list[PaperPosition]:
        with self._lock:
            session = self._session()
            try:
                rows = session.scalars(
                    select(PaperPositionRow).where(
                        PaperPositionRow.session_id == session_id,
                        PaperPositionRow.status == PositionStatus.OPEN.value,
                        PaperPositionRow.owner_user_id == self._owner,
                    )
                ).all()
                return [self._row_to_position(r) for r in rows]
            finally:
                session.close()

    def get_open_position_for_symbol(
        self, session_id: str, symbol: str
    ) -> PaperPosition | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperPositionRow).where(
                        PaperPositionRow.session_id == session_id,
                        PaperPositionRow.symbol == symbol,
                        PaperPositionRow.status == PositionStatus.OPEN.value,
                        PaperPositionRow.owner_user_id == self._owner,
                    )
                )
                return self._row_to_position(row) if row else None
            finally:
                session.close()

    def get_position(self, position_id: str) -> PaperPosition | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperPositionRow).where(
                        PaperPositionRow.position_id == position_id,
                        PaperPositionRow.owner_user_id == self._owner,
                    )
                )
                return self._row_to_position(row) if row else None
            finally:
                session.close()

    def close_position(
        self,
        conn: Any,
        *,
        position_id: str,
        exit_price: Decimal,
        exit_fee: Decimal,
        exit_order_id: str,
        exit_reason: str,
        realized_pnl: Decimal,
        closed_ms: int,
    ) -> None:
        result = conn.execute(
            update(PaperPositionRow)
            .where(
                PaperPositionRow.position_id == position_id,
                PaperPositionRow.status == PositionStatus.OPEN.value,
                PaperPositionRow.owner_user_id == self._owner,
            )
            .values(
                status=PositionStatus.CLOSED.value,
                closed_ms=closed_ms,
                exit_price=str(exit_price),
                exit_fee=str(exit_fee),
                exit_order_id=exit_order_id,
                exit_reason=exit_reason,
                realized_pnl=str(realized_pnl),
                unrealized_pnl="0",
            )
        )
        if result.rowcount == 0:
            raise RuntimeError(f"position {position_id} already closed or missing")

    def mark_position(
        self,
        conn: Any,
        *,
        position_id: str,
        mark_price: Decimal,
        unrealized_pnl: Decimal,
    ) -> None:
        conn.execute(
            update(PaperPositionRow)
            .where(
                PaperPositionRow.position_id == position_id,
                PaperPositionRow.status == PositionStatus.OPEN.value,
                PaperPositionRow.owner_user_id == self._owner,
            )
            .values(mark_price=str(mark_price), unrealized_pnl=str(unrealized_pnl))
        )

    def get_candle_cursor(
        self, session_id: str, symbol: str, interval: str
    ) -> int | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperCandleCursorRow).where(
                        PaperCandleCursorRow.owner_user_id == self._owner,
                        PaperCandleCursorRow.session_id == session_id,
                        PaperCandleCursorRow.symbol == symbol,
                        PaperCandleCursorRow.interval == interval,
                    )
                )
                return int(row.last_candle_start_ms) if row else None
            finally:
                session.close()

    def set_candle_cursor(
        self,
        conn: Any,
        *,
        session_id: str,
        symbol: str,
        interval: str,
        candle_start_ms: int,
    ) -> None:
        existing = conn.scalar(
            select(PaperCandleCursorRow).where(
                PaperCandleCursorRow.owner_user_id == self._owner,
                PaperCandleCursorRow.session_id == session_id,
                PaperCandleCursorRow.symbol == symbol,
                PaperCandleCursorRow.interval == interval,
            )
        )
        if existing is None:
            conn.add(
                PaperCandleCursorRow(
                    owner_user_id=self._owner,
                    session_id=session_id,
                    symbol=symbol,
                    interval=interval,
                    last_candle_start_ms=candle_start_ms,
                )
            )
        elif candle_start_ms > existing.last_candle_start_ms:
            existing.last_candle_start_ms = candle_start_ms

    def has_processed_event(self, session_id: str, event_key: str) -> bool:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperProcessedEventRow).where(
                        PaperProcessedEventRow.owner_user_id == self._owner,
                        PaperProcessedEventRow.session_id == session_id,
                        PaperProcessedEventRow.event_key == event_key,
                    )
                )
                return row is not None
            finally:
                session.close()

    def mark_processed_event(
        self,
        conn: Any,
        *,
        session_id: str,
        event_key: str,
        created_ms: int,
    ) -> bool:
        existing = conn.scalar(
            select(PaperProcessedEventRow).where(
                PaperProcessedEventRow.owner_user_id == self._owner,
                PaperProcessedEventRow.session_id == session_id,
                PaperProcessedEventRow.event_key == event_key,
            )
        )
        if existing is not None:
            return False
        conn.add(
            PaperProcessedEventRow(
                owner_user_id=self._owner,
                session_id=session_id,
                event_key=event_key,
                created_ms=created_ms,
            )
        )
        return True

    def _append_event(
        self,
        conn: Any,
        *,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        created_ms: int,
        idempotency_key: str,
    ) -> None:
        exists = conn.scalar(
            select(PaperAccountEventRow).where(
                PaperAccountEventRow.session_id == session_id,
                PaperAccountEventRow.idempotency_key == idempotency_key,
            )
        )
        if exists is not None:
            return
        conn.add(
            PaperAccountEventRow(
                event_id=new_id("pe"),
                owner_user_id=self._owner,
                session_id=session_id,
                event_type=event_type,
                payload_json=json.dumps(payload, separators=(",", ":")),
                created_ms=created_ms,
                idempotency_key=idempotency_key,
            )
        )

    def append_event(
        self,
        conn: Any,
        *,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        created_ms: int,
        idempotency_key: str,
    ) -> None:
        self._append_event(
            conn,
            session_id=session_id,
            event_type=event_type,
            payload=payload,
            created_ms=created_ms,
            idempotency_key=idempotency_key,
        )

    def list_account_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            session = self._session()
            try:
                rows = session.scalars(
                    select(PaperAccountEventRow)
                    .where(
                        PaperAccountEventRow.session_id == session_id,
                        PaperAccountEventRow.owner_user_id == self._owner,
                    )
                    .order_by(PaperAccountEventRow.created_ms.asc())
                ).all()
                return [
                    {
                        "event_id": r.event_id,
                        "session_id": r.session_id,
                        "event_type": r.event_type,
                        "payload_json": r.payload_json,
                        "created_ms": r.created_ms,
                        "idempotency_key": r.idempotency_key,
                    }
                    for r in rows
                ]
            finally:
                session.close()

    def get_risk_state(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperRiskStateRow).where(
                        PaperRiskStateRow.session_id == session_id,
                        PaperRiskStateRow.owner_user_id == self._owner,
                    )
                )
                if row is None:
                    return None
                return {
                    "session_id": row.session_id,
                    "halted": int(row.halted),
                    "halt_reason": row.halt_reason,
                    "halt_ms": row.halt_ms,
                    "peak_marked_equity": row.peak_marked_equity,
                    "day_key": row.day_key,
                    "day_start_equity": row.day_start_equity,
                    "updated_ms": row.updated_ms,
                }
            finally:
                session.close()

    def upsert_risk_state(
        self,
        conn: Any,
        *,
        session_id: str,
        halted: bool,
        halt_reason: str | None,
        halt_ms: int | None,
        peak_marked_equity: Decimal | None,
        day_key: str | None,
        day_start_equity: Decimal | None,
        updated_ms: int,
    ) -> None:
        values = {
            "session_id": session_id,
            "owner_user_id": self._owner,
            "halted": halted,
            "halt_reason": halt_reason,
            "halt_ms": halt_ms,
            "peak_marked_equity": (
                str(peak_marked_equity) if peak_marked_equity is not None else None
            ),
            "day_key": day_key,
            "day_start_equity": (
                str(day_start_equity) if day_start_equity is not None else None
            ),
            "updated_ms": updated_ms,
        }
        if conn.bind and conn.bind.dialect.name == "postgresql":
            stmt = pg_insert(PaperRiskStateRow).values(**values)
            stmt = stmt.on_conflict_do_update(
                index_elements=[PaperRiskStateRow.session_id],
                set_={k: v for k, v in values.items() if k not in {"session_id", "owner_user_id"}},
            )
            conn.execute(stmt)
        else:
            existing = conn.scalar(
                select(PaperRiskStateRow).where(PaperRiskStateRow.session_id == session_id)
            )
            if existing is None:
                conn.add(PaperRiskStateRow(**values))
            else:
                for k, v in values.items():
                    setattr(existing, k, v)

    def insert_equity_snapshot(
        self,
        conn: Any,
        *,
        session_id: str,
        as_of_ms: int,
        available: Decimal,
        reserved: Decimal,
        realized_pnl: Decimal,
        unrealized_pnl: Decimal | None,
        marked_equity: Decimal | None,
        valuation_status: str,
        open_position_count: int,
        gross_exposure: Decimal,
        day_key: str,
    ) -> None:
        try:
            conn.add(
                PaperEquitySnapshotRow(
                    snapshot_id=new_id("eq"),
                    owner_user_id=self._owner,
                    session_id=session_id,
                    as_of_ms=as_of_ms,
                    available_balance=str(available),
                    reserved_capital=str(reserved),
                    realized_pnl=str(realized_pnl),
                    unrealized_pnl=str(unrealized_pnl) if unrealized_pnl is not None else None,
                    marked_equity=str(marked_equity) if marked_equity is not None else None,
                    valuation_status=valuation_status,
                    open_position_count=open_position_count,
                    gross_exposure=str(gross_exposure),
                    day_key=day_key,
                )
            )
            conn.flush()
        except IntegrityError:
            conn.rollback()

    def latest_equity_snapshot(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._session()
            try:
                row = session.scalar(
                    select(PaperEquitySnapshotRow)
                    .where(
                        PaperEquitySnapshotRow.session_id == session_id,
                        PaperEquitySnapshotRow.owner_user_id == self._owner,
                    )
                    .order_by(PaperEquitySnapshotRow.as_of_ms.desc())
                    .limit(1)
                )
                if row is None:
                    return None
                return {
                    "snapshot_id": row.snapshot_id,
                    "session_id": row.session_id,
                    "as_of_ms": row.as_of_ms,
                    "available_balance": row.available_balance,
                    "reserved_capital": row.reserved_capital,
                    "realized_pnl": row.realized_pnl,
                    "unrealized_pnl": row.unrealized_pnl,
                    "marked_equity": row.marked_equity,
                    "valuation_status": row.valuation_status,
                    "open_position_count": row.open_position_count,
                    "gross_exposure": row.gross_exposure,
                    "day_key": row.day_key,
                }
            finally:
                session.close()

    @staticmethod
    def _row_to_session(row: PaperSessionRow) -> PaperSession:
        return PaperSession(
            session_id=row.session_id,
            initial_balance=d(row.initial_balance),
            available_balance=d(row.available_balance),
            reserved_capital=d(row.reserved_capital),
            realized_pnl=d(row.realized_pnl),
            fees_paid=d(row.fees_paid),
            status=SessionStatus(row.status),
            created_ms=int(row.created_ms),
            updated_ms=int(row.updated_ms),
            config_json=row.config_json,
            currency=row.currency,
        )

    @staticmethod
    def _row_to_order(row: PaperOrderRow) -> PaperOrder:
        return PaperOrder(
            order_id=row.order_id,
            session_id=row.session_id,
            source_signal_id=row.source_signal_id,
            symbol=row.symbol,
            category=row.category,
            side=OrderSide(row.side),
            quantity=d(row.quantity),
            intended_entry_price=d(row.intended_entry_price),
            status=OrderStatus(row.status),
            created_ms=int(row.created_ms),
            filled_ms=int(row.filled_ms) if row.filled_ms is not None else None,
            fill_price=d(row.fill_price) if row.fill_price is not None else None,
            fee=d(row.fee),
            slippage=d(row.slippage),
            rejection_reason=row.rejection_reason,
            stop_loss=d(row.stop_loss) if row.stop_loss is not None else None,
            take_profit=d(row.take_profit) if row.take_profit is not None else None,
            signal_candle_start_ms=row.signal_candle_start_ms,
            simulated=bool(row.simulated),
        )

    @staticmethod
    def _row_to_position(row: PaperPositionRow) -> PaperPosition:
        return PaperPosition(
            position_id=row.position_id,
            session_id=row.session_id,
            symbol=row.symbol,
            category=row.category,
            status=PositionStatus(row.status),
            quantity=d(row.quantity),
            entry_price=d(row.entry_price),
            entry_fee=d(row.entry_fee),
            entry_order_id=row.entry_order_id,
            entry_signal_id=row.entry_signal_id,
            stop_loss=d(row.stop_loss) if row.stop_loss is not None else None,
            take_profit=d(row.take_profit) if row.take_profit is not None else None,
            opened_ms=int(row.opened_ms),
            closed_ms=int(row.closed_ms) if row.closed_ms is not None else None,
            exit_price=d(row.exit_price) if row.exit_price is not None else None,
            exit_fee=d(row.exit_fee),
            exit_order_id=row.exit_order_id,
            exit_reason=row.exit_reason,
            realized_pnl=d(row.realized_pnl),
            mark_price=d(row.mark_price) if row.mark_price is not None else None,
            unrealized_pnl=d(row.unrealized_pnl),
        )
