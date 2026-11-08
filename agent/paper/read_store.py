"""Read-only access to paper broker state via SQLAlchemy (no sqlite3)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from agent.paper.config import d
from agent.paper.models import (
    OrderSide,
    PaperFill,
    PaperOrder,
    PaperPosition,
    PaperSession,
    PositionStatus,
)
from agent.paper.store import PaperStore
from apps.api.app.config import get_api_settings
from apps.api.app.persistence.paper_models import (
    PaperAccountEventRow,
    PaperEquitySnapshotRow,
    PaperMetaRow,
    PaperOrderRow,
    PaperPositionRow,
    PaperSessionRow,
)
from apps.api.app.persistence.sqlite_guard import supabase_sot_enabled


class PaperDbUnavailable(Exception):
    """Database missing, unreadable, or not a paper schema."""


class PaperReadStore:
    """Query persisted paper broker state without writes or schema init."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._store: PaperStore | None = None
        self._unreadable = False
        if supabase_sot_enabled():
            self._store = PaperStore(None)
        elif self.db_path.is_file():
            try:
                self._store = PaperStore(self.db_path)
            except Exception:  # noqa: BLE001 — corrupt / non-sqlite file
                self._unreadable = True

    def exists(self) -> bool:
        if supabase_sot_enabled():
            return get_api_settings().database_configured
        return self.db_path.is_file()

    def _require_store(self) -> PaperStore:
        if self._store is None:
            raise PaperDbUnavailable("paper_db_missing")
        return self._store

    def schema_version(self) -> int | None:
        if not self.exists():
            raise PaperDbUnavailable("paper_db_missing")
        if self._unreadable:
            raise PaperDbUnavailable("paper_schema_invalid")
        store = self._require_store()
        session = store._Session()
        try:
            row = session.scalar(
                select(PaperMetaRow).where(
                    PaperMetaRow.owner_user_id == store._owner,
                    PaperMetaRow.key == "schema_version",
                )
            )
            if row is None:
                return None
            return int(row.value)
        except Exception as exc:
            raise PaperDbUnavailable("paper_schema_invalid") from exc
        finally:
            session.close()

    def list_sessions(self, *, limit: int = 50, offset: int = 0) -> list[PaperSession]:
        limit = max(1, min(int(limit), 100))
        offset = max(0, int(offset))
        store = self._require_store()
        session = store._Session()
        try:
            rows = session.scalars(
                select(PaperSessionRow)
                .where(PaperSessionRow.owner_user_id == self._require_store()._owner)
                .order_by(PaperSessionRow.updated_ms.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            return [PaperStore._row_to_session(r) for r in rows]
        finally:
            session.close()

    def count_sessions(self) -> int:
        session = self._require_store()._Session()
        try:
            n = session.scalar(
                select(func.count())
                .select_from(PaperSessionRow)
                .where(PaperSessionRow.owner_user_id == self._require_store()._owner)
            )
            return int(n or 0)
        finally:
            session.close()

    def get_session(self, session_id: str) -> PaperSession | None:
        return self._require_store().get_session(session_id)

    def count_open_positions(self, session_id: str) -> int:
        session = self._require_store()._Session()
        try:
            n = session.scalar(
                select(func.count())
                .select_from(PaperPositionRow)
                .where(
                    PaperPositionRow.session_id == session_id,
                    PaperPositionRow.status == PositionStatus.OPEN.value,
                    PaperPositionRow.owner_user_id == self._require_store()._owner,
                )
            )
            return int(n or 0)
        finally:
            session.close()

    def sum_open_unrealized(self, session_id: str) -> tuple[Decimal | None, bool]:
        session = self._require_store()._Session()
        try:
            rows = session.scalars(
                select(PaperPositionRow).where(
                    PaperPositionRow.session_id == session_id,
                    PaperPositionRow.status == PositionStatus.OPEN.value,
                    PaperPositionRow.owner_user_id == self._require_store()._owner,
                )
            ).all()
        finally:
            session.close()
        if not rows:
            return Decimal("0"), True
        total = Decimal("0")
        all_present = True
        for r in rows:
            if r.mark_price is None:
                all_present = False
                continue
            total += d(r.unrealized_pnl or "0")
        return total, all_present

    def list_positions(
        self,
        session_id: str,
        *,
        status: str | None = None,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PaperPosition]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        session = self._require_store()._Session()
        try:
            stmt = select(PaperPositionRow).where(
                PaperPositionRow.session_id == session_id,
                PaperPositionRow.owner_user_id == self._require_store()._owner,
            )
            if status:
                stmt = stmt.where(PaperPositionRow.status == status)
            if symbol:
                stmt = stmt.where(PaperPositionRow.symbol == symbol)
            rows = session.scalars(
                stmt.order_by(PaperPositionRow.opened_ms.desc()).limit(limit).offset(offset)
            ).all()
            return [PaperStore._row_to_position(r) for r in rows]
        finally:
            session.close()

    def list_orders(
        self,
        session_id: str,
        *,
        status: str | None = None,
        symbol: str | None = None,
        source_signal_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PaperOrder]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        session = self._require_store()._Session()
        try:
            stmt = select(PaperOrderRow).where(
                PaperOrderRow.session_id == session_id,
                PaperOrderRow.owner_user_id == self._require_store()._owner,
            )
            if status:
                stmt = stmt.where(PaperOrderRow.status == status)
            if symbol:
                stmt = stmt.where(PaperOrderRow.symbol == symbol)
            if source_signal_id:
                stmt = stmt.where(PaperOrderRow.source_signal_id == source_signal_id)
            rows = session.scalars(
                stmt.order_by(PaperOrderRow.created_ms.desc()).limit(limit).offset(offset)
            ).all()
            return [PaperStore._row_to_order(r) for r in rows]
        finally:
            session.close()

    def list_fills(
        self,
        session_id: str,
        *,
        symbol: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[PaperFill]:
        from apps.api.app.persistence.paper_models import PaperFillRow

        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        session = self._require_store()._Session()
        try:
            stmt = select(PaperFillRow).where(
                PaperFillRow.session_id == session_id,
                PaperFillRow.owner_user_id == self._require_store()._owner,
            )
            if symbol:
                stmt = stmt.where(PaperFillRow.symbol == symbol)
            rows = session.scalars(
                stmt.order_by(PaperFillRow.filled_ms.desc()).limit(limit).offset(offset)
            ).all()
            return [_row_to_fill(r) for r in rows]
        finally:
            session.close()

    def list_events(
        self,
        session_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        session = self._require_store()._Session()
        try:
            rows = session.scalars(
                select(PaperAccountEventRow)
                .where(
                    PaperAccountEventRow.session_id == session_id,
                    PaperAccountEventRow.owner_user_id == self._require_store()._owner,
                )
                .order_by(PaperAccountEventRow.created_ms.desc())
                .limit(limit)
                .offset(offset)
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

    def find_orders_by_signal(
        self, source_signal_id: str, *, limit: int = 20
    ) -> list[PaperOrder]:
        limit = max(1, min(int(limit), 50))
        session = self._require_store()._Session()
        try:
            rows = session.scalars(
                select(PaperOrderRow)
                .where(
                    PaperOrderRow.owner_user_id == self._require_store()._owner,
                    PaperOrderRow.source_signal_id == source_signal_id,
                )
                .order_by(PaperOrderRow.created_ms.desc())
                .limit(limit)
            ).all()
            return [PaperStore._row_to_order(r) for r in rows]
        finally:
            session.close()

    def list_closed_positions(
        self,
        session_id: str,
        *,
        symbol: str | None = None,
        exit_from_ms: int | None = None,
        exit_to_ms: int | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[PaperPosition]:
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))
        session = self._require_store()._Session()
        try:
            stmt = select(PaperPositionRow).where(
                PaperPositionRow.session_id == session_id,
                PaperPositionRow.status == PositionStatus.CLOSED.value,
                PaperPositionRow.owner_user_id == self._require_store()._owner,
            )
            if symbol:
                stmt = stmt.where(PaperPositionRow.symbol == symbol)
            if exit_from_ms is not None:
                stmt = stmt.where(PaperPositionRow.closed_ms >= int(exit_from_ms))
            if exit_to_ms is not None:
                stmt = stmt.where(PaperPositionRow.closed_ms <= int(exit_to_ms))
            rows = session.scalars(
                stmt.order_by(PaperPositionRow.closed_ms.asc()).limit(limit).offset(offset)
            ).all()
            return [PaperStore._row_to_position(r) for r in rows]
        finally:
            session.close()

    def list_equity_snapshots(
        self,
        session_id: str,
        *,
        from_ms: int | None = None,
        to_ms: int | None = None,
        limit: int = 2000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 5000))
        offset = max(0, int(offset))
        session = self._require_store()._Session()
        try:
            stmt = select(PaperEquitySnapshotRow).where(
                PaperEquitySnapshotRow.session_id == session_id,
                PaperEquitySnapshotRow.owner_user_id == self._require_store()._owner,
            )
            if from_ms is not None:
                stmt = stmt.where(PaperEquitySnapshotRow.as_of_ms >= int(from_ms))
            if to_ms is not None:
                stmt = stmt.where(PaperEquitySnapshotRow.as_of_ms <= int(to_ms))
            rows = session.scalars(
                stmt.order_by(PaperEquitySnapshotRow.as_of_ms.asc()).limit(limit).offset(offset)
            ).all()
            return [
                {
                    "snapshot_id": r.snapshot_id,
                    "session_id": r.session_id,
                    "as_of_ms": r.as_of_ms,
                    "available_balance": r.available_balance,
                    "reserved_capital": r.reserved_capital,
                    "realized_pnl": r.realized_pnl,
                    "unrealized_pnl": r.unrealized_pnl,
                    "marked_equity": r.marked_equity,
                    "valuation_status": r.valuation_status,
                    "open_position_count": r.open_position_count,
                    "gross_exposure": r.gross_exposure,
                    "day_key": r.day_key,
                }
                for r in rows
            ]
        except Exception as exc:
            raise PaperDbUnavailable("paper_equity_snapshots_unreadable") from exc
        finally:
            session.close()


def _row_to_fill(row: Any) -> PaperFill:
    return PaperFill(
        fill_id=row.fill_id,
        order_id=row.order_id,
        session_id=row.session_id,
        symbol=row.symbol,
        side=OrderSide(row.side),
        quantity=d(row.quantity),
        price=d(row.price),
        fee=d(row.fee),
        slippage=d(row.slippage),
        filled_ms=int(row.filled_ms),
        candle_start_ms=int(row.candle_start_ms),
        role=row.role,
    )
