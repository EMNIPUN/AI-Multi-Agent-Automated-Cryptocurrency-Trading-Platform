"""
Append-only worker telemetry ledger.

This file is not the execution, fill, or risk source of truth.
Writes never raise to the caller of ``safe_record``.
Payloads are sanitized before insert. Account fingerprints are not stored.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from apps.api.app.persistence.ledger_models import ObservationEventRow
from apps.api.app.persistence.owner import resolve_sot_owner_user_id
from apps.api.app.persistence.sqlite_guard import (
    agent_sessionmaker,
    bootstrap_agent_schema,
    create_agent_engine,
)

from apps.api.app.observability.types import (
    SCHEMA_VERSION,
    AgentRuntimeStatus,
    AgentSnapshot,
    CandleBar,
    DataMode,
    ExecutionMode,
    ObservabilityEvent,
    ObservabilityEventType,
    OrderLifecycleItem,
    PipelineStep,
    SignalMarker,
)
from apps.api.app.sanitize import sanitize_public_json

_MAX_ROWS = 5_000

_STEP_BY_TYPE: dict[str, PipelineStep] = {
    "market.candle_confirmed": PipelineStep.CONFIRMED_CANDLE,
    "analysis.completed": PipelineStep.STRATEGY,
    "signal.generated": PipelineStep.SIGNAL,
    "risk.approved": PipelineStep.RISK,
    "risk.blocked": PipelineStep.BLOCKED,
    "risk.halted": PipelineStep.HALTED,
    "order.intent_created": PipelineStep.INTENT,
    "order.accepted": PipelineStep.INTENT,
    "order.partially_filled": PipelineStep.RECONCILIATION,
    "order.filled": PipelineStep.RECONCILIATION,
    "order.canceled": PipelineStep.RECONCILIATION,
    "order.reconciliation_required": PipelineStep.RECONCILIATION,
}


def make_event(
    *,
    event_type: ObservabilityEventType,
    event_id: str,
    message: str,
    symbol: str | None = None,
    interval: str | None = None,
    correlation_id: str | None = None,
    env_scope: str = "local",
    account_scope_label: str | None = None,
    execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
    pipeline_step: PipelineStep | None = None,
    payload: dict | None = None,
) -> ObservabilityEvent:
    # Non-secret scope only — never account_fp / API keys.
    # Binding telemetry_scope_id is a UUID (36 chars); allow that explicitly.
    scope = (account_scope_label or "operator-local").strip() or "operator-local"
    if not _is_allowed_telemetry_scope(scope):
        scope = "operator-local"
    return ObservabilityEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=_utc_now(),
        correlation_id=correlation_id,
        env_scope=env_scope,
        account_scope_label=scope,
        symbol=symbol,
        interval=interval,
        execution_mode=execution_mode,
        pipeline_step=pipeline_step,
        message=message[:500],
        payload=payload or {},
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class TelemetryLedger:
    def __init__(self, path: str | Path, *, max_rows: int = _MAX_ROWS) -> None:
        self.path = Path(path)
        self.max_rows = max_rows
        self._owner = resolve_sot_owner_user_id()
        self._engine = create_agent_engine(path)
        bootstrap_agent_schema(self._engine)
        self._Session = agent_sessionmaker(self._engine)
        self._lock = threading.RLock()

    def record(self, event: ObservabilityEvent) -> bool:
        payload = sanitize_public_json(event.payload)
        if not isinstance(payload, dict):
            payload = {}
        body = event.model_copy(update={"payload": payload, "account_scope_label": _scope_label(event)})
        with self._lock:
            session = self._Session()
            try:
                exists = session.scalar(
                    select(ObservationEventRow).where(
                        ObservationEventRow.owner_user_id == self._owner,
                        ObservationEventRow.event_id == body.event_id,
                    )
                )
                if exists is not None:
                    return False
                session.add(
                    ObservationEventRow(
                        owner_user_id=self._owner,
                        event_id=body.event_id,
                        event_type=body.event_type.value,
                        occurred_at=body.occurred_at.astimezone(timezone.utc).isoformat(),
                        correlation_id=body.correlation_id,
                        env_scope=body.env_scope,
                        account_scope_label=body.account_scope_label,
                        symbol=body.symbol,
                        interval=body.interval,
                        execution_mode=body.execution_mode.value,
                        pipeline_step=(
                            body.pipeline_step.value if body.pipeline_step else None
                        ),
                        message=body.message[:500],
                        payload_json=body.payload,
                    )
                )
                session.commit()
                self._trim(session)
                return True
            except IntegrityError:
                session.rollback()
                return False
            except SQLAlchemyError:
                session.rollback()
                raise
            finally:
                session.close()

    def safe_record(self, event: ObservabilityEvent) -> bool:
        try:
            return self.record(event)
        except Exception:
            return False

    def _trim(self, session) -> None:  # noqa: ANN001
        keep = session.scalars(
            select(ObservationEventRow.seq)
            .where(ObservationEventRow.owner_user_id == self._owner)
            .order_by(ObservationEventRow.seq.desc())
            .limit(self.max_rows)
        ).all()
        if not keep:
            return
        session.execute(
            delete(ObservationEventRow).where(
                ObservationEventRow.owner_user_id == self._owner,
                ObservationEventRow.seq.not_in(keep),
            )
        )
        session.commit()

    def count(self) -> int:
        with self._lock:
            session = self._Session()
            try:
                n = session.scalar(
                    select(func.count())
                    .select_from(ObservationEventRow)
                    .where(ObservationEventRow.owner_user_id == self._owner)
                )
                return int(n or 0)
            finally:
                session.close()

    def since(self, cursor: str | None, *, limit: int = 200) -> list[ObservabilityEvent]:
        limit = max(1, min(limit, 500))
        with self._lock:
            session = self._Session()
            try:
                stmt = (
                    select(ObservationEventRow)
                    .where(ObservationEventRow.owner_user_id == self._owner)
                    .order_by(ObservationEventRow.seq.asc())
                    .limit(limit)
                )
                if cursor and cursor.isdigit():
                    stmt = stmt.where(ObservationEventRow.seq > int(cursor))
                rows = session.scalars(stmt).all()
                return [_row_to_event(r) for r in rows]
            finally:
                session.close()

    def latest_cursor(self) -> str | None:
        with self._lock:
            session = self._Session()
            try:
                seq = session.scalar(
                    select(func.max(ObservationEventRow.seq)).where(
                        ObservationEventRow.owner_user_id == self._owner
                    )
                )
                return str(seq) if seq is not None else None
            finally:
                session.close()

    def snapshot(self, *, stale_after_seconds: int = 120, limit: int = 100) -> AgentSnapshot:
        events = self._newest(limit)
        now = _utc_now()
        heartbeat = self._last_of_type(ObservabilityEventType.AGENT_HEARTBEAT)
        stopped = self._last_of_type(ObservabilityEventType.AGENT_STOPPED)
        halt = self._last_of_type(ObservabilityEventType.RISK_HALTED) or self._last_of_type(
            ObservabilityEventType.AGENT_HALTED
        )
        heartbeat_at = heartbeat.occurred_at if heartbeat else None
        stopped_at = stopped.occurred_at if stopped else None
        stale = True
        if heartbeat_at is None:
            status = AgentRuntimeStatus.UNKNOWN
        else:
            stale = now - heartbeat_at > timedelta(seconds=stale_after_seconds)
            if stopped_at and stopped_at >= heartbeat_at:
                status = AgentRuntimeStatus.OFFLINE
                stale = True
            elif halt and halt.occurred_at >= heartbeat_at:
                status = AgentRuntimeStatus.HALTED
            elif stale:
                status = AgentRuntimeStatus.OFFLINE
            else:
                status = AgentRuntimeStatus.RUNNING

        signal = self._last_of_type(ObservabilityEventType.SIGNAL_GENERATED)
        analysis = self._last_of_type(ObservabilityEventType.ANALYSIS_COMPLETED)
        candle = self._last_of_type(ObservabilityEventType.MARKET_CANDLE_CONFIRMED)
        approved = self._last_of_type(ObservabilityEventType.RISK_APPROVED)
        blocked = self._last_of_type(ObservabilityEventType.RISK_BLOCKED)
        latest = events[-1] if events else None
        risk_verdict = "N/A"
        risk_reasons: list[str] = []
        if halt and (not heartbeat_at or halt.occurred_at >= heartbeat_at):
            risk_verdict = "UNKNOWN"
            risk_reasons = [halt.message]
        if blocked and (not approved or blocked.occurred_at >= approved.occurred_at):
            risk_verdict = "BLOCKED"
            risk_reasons = [blocked.message]
        elif approved and (not blocked or approved.occurred_at > blocked.occurred_at):
            risk_verdict = "APPROVED"
            risk_reasons = [approved.message]

        signal_action = None
        signal_reason = None
        if signal and signal.payload.get("action") in {"BUY", "SELL", "HOLD"}:
            signal_action = signal.payload["action"]
            signal_reason = signal.message

        step = PipelineStep.UNKNOWN
        blocked_pipe = risk_verdict == "BLOCKED" or status is AgentRuntimeStatus.HALTED
        if status is AgentRuntimeStatus.HALTED:
            step = PipelineStep.HALTED
        elif latest and latest.event_type.value in _STEP_BY_TYPE:
            step = _STEP_BY_TYPE[latest.event_type.value]

        symbol = (signal or analysis or candle or latest).symbol if (signal or analysis or candle or latest) else "—"
        interval = (candle or latest).interval if (candle or latest) and (candle or latest).interval else "—"
        mode = latest.execution_mode if latest else ExecutionMode.DRY_RUN
        orders = _orders_from_events(events)
        candles = _candles_from_events(events)
        markers = _markers_from_events(events)

        return AgentSnapshot(
            schema_version=SCHEMA_VERSION,
            data_mode=DataMode.LIVE,
            sample_label=None,
            generated_at=now,
            agent_status=status,
            heartbeat_at=heartbeat_at,
            heartbeat_stale=stale,
            stale_after_seconds=stale_after_seconds,
            symbol=symbol or "—",
            interval=interval or "—",
            execution_mode=mode,
            money_view="real_readonly",
            last_confirmed_candle_at=_parse_dt(
                str(candle.payload.get("candle_close_at")) if candle and candle.payload.get("candle_close_at") else None
            ),
            ema_fast=_num(analysis.payload.get("ema_fast") if analysis else None),
            ema_slow=_num(analysis.payload.get("ema_slow") if analysis else None),
            rsi=_num(analysis.payload.get("rsi") if analysis else None),
            signal_action=signal_action,
            signal_reason=signal_reason,
            risk_verdict=risk_verdict,  # type: ignore[arg-type]
            risk_reasons=risk_reasons,
            current_pipeline_step=step,
            pipeline_blocked=blocked_pipe,
            pipeline_block_reason=risk_reasons[0] if blocked_pipe and risk_reasons else None,
            candles=candles,
            markers=markers,
            orders=orders,
            events=events,
            cursor=self.latest_cursor(),
            notes=[
                "Worker telemetry ledger. Not exchange authority.",
                "HOLD is a signal, not a trade.",
                "ACCEPTED is not FILLED.",
                "Candles/markers come only from recorded confirmed-bar evidence.",
            ],
        )

    def _last_of_type(self, kind: ObservabilityEventType) -> ObservabilityEvent | None:
        with self._lock:
            session = self._Session()
            try:
                row = session.scalar(
                    select(ObservationEventRow)
                    .where(
                        ObservationEventRow.owner_user_id == self._owner,
                        ObservationEventRow.event_type == kind.value,
                    )
                    .order_by(ObservationEventRow.seq.desc())
                    .limit(1)
                )
                return _row_to_event(row) if row else None
            finally:
                session.close()

    def _newest(self, limit: int) -> list[ObservabilityEvent]:
        limit = max(1, min(limit, 500))
        with self._lock:
            session = self._Session()
            try:
                rows = session.scalars(
                    select(ObservationEventRow)
                    .where(ObservationEventRow.owner_user_id == self._owner)
                    .order_by(ObservationEventRow.seq.desc())
                    .limit(limit)
                ).all()
                return [_row_to_event(row) for row in reversed(rows)]
            finally:
                session.close()


def unavailable_snapshot(reason: str) -> AgentSnapshot:
    now = _utc_now()
    return AgentSnapshot(
        schema_version=SCHEMA_VERSION,
        data_mode=DataMode.UNAVAILABLE,
        sample_label=None,
        generated_at=now,
        agent_status=AgentRuntimeStatus.UNKNOWN,
        heartbeat_at=None,
        heartbeat_stale=True,
        symbol="—",
        interval="—",
        execution_mode=ExecutionMode.DRY_RUN,
        money_view="real_readonly",
        current_pipeline_step=PipelineStep.UNKNOWN,
        events=[],
        notes=[reason, "SAMPLE fixtures are not mixed into this response."],
    )


_UUID_SCOPE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_allowed_telemetry_scope(label: str) -> bool:
    """
    Accept operator-local labels and binding UUIDs only.
    Reject fingerprint-like or overlong secret-adjacent strings.
    """
    text = label.strip()
    if not text or len(text) > 64:
        return False
    lowered = text.lower()
    if lowered.startswith("fp") or lowered.startswith("fp:") or "account_fp" in lowered:
        return False
    if lowered == "operator-local":
        return True
    if _UUID_SCOPE_RE.fullmatch(text):
        return True
    # Short non-secret labels (env tags) — no colons that look like key material.
    if len(text) <= 32 and ":" not in text and " " not in text:
        return True
    return False


def _scope_label(event: ObservabilityEvent) -> str | None:
    label = event.account_scope_label or "operator-local"
    if not _is_allowed_telemetry_scope(label):
        return "operator-local"
    return label.strip()


def _last(events: list[ObservabilityEvent], kind: ObservabilityEventType) -> ObservabilityEvent | None:
    found = [e for e in events if e.event_type is kind]
    return found[-1] if found else None


def _num(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _candles_from_events(events: list[ObservabilityEvent]) -> list[CandleBar]:
    """Use the newest market.candle_confirmed recent_bars payload when present."""
    for event in reversed(events):
        if event.event_type is not ObservabilityEventType.MARKET_CANDLE_CONFIRMED:
            continue
        bars = event.payload.get("recent_bars")
        if not isinstance(bars, list) or not bars:
            # Single-bar fallback from OHLCV fields.
            t = event.payload.get("candle_start_ms")
            if isinstance(t, (int, float)):
                return [
                    CandleBar(
                        time=int(t) // 1000,
                        open=float(event.payload.get("open") or 0),
                        high=float(event.payload.get("high") or 0),
                        low=float(event.payload.get("low") or 0),
                        close=float(event.payload.get("close") or 0),
                        volume=_num(event.payload.get("volume")),
                    )
                ]
            continue
        out: list[CandleBar] = []
        seen: set[int] = set()
        for raw in bars:
            if not isinstance(raw, dict):
                continue
            try:
                time_s = int(raw["time"])
                if time_s in seen:
                    continue
                seen.add(time_s)
                out.append(
                    CandleBar(
                        time=time_s,
                        open=float(raw["open"]),
                        high=float(raw["high"]),
                        low=float(raw["low"]),
                        close=float(raw["close"]),
                        volume=_num(raw.get("volume")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        out.sort(key=lambda b: b.time)
        return out
    return []


def _markers_from_events(events: list[ObservabilityEvent]) -> list[SignalMarker]:
    """Emit markers only when candle open-time evidence is present and verified."""
    candle_times = {c.time for c in _candles_from_events(events)}
    markers: list[SignalMarker] = []
    for event in events:
        if event.event_type is not ObservabilityEventType.SIGNAL_GENERATED:
            continue
        action = event.payload.get("action")
        if action not in {"BUY", "SELL", "HOLD"}:
            continue
        start_ms = event.payload.get("candle_start_ms")
        if not isinstance(start_ms, (int, float)):
            # Do not invent chart time from occurred_at when bars exist.
            continue
        time_s = int(start_ms) // 1000
        if candle_times and time_s not in candle_times:
            continue
        if not candle_times:
            continue
        price = _num(event.payload.get("price")) or 0.0
        markers.append(
            SignalMarker(
                time=time_s,
                action=action,  # type: ignore[arg-type]
                price=price,
                label=str(event.payload.get("explanation_code") or action),
                sample=False,
            )
        )
    return markers


def _orders_from_events(events: list[ObservabilityEvent]) -> list[OrderLifecycleItem]:
    """Latest evidenced state per client_order_id / intent_id (ACCEPTED ≠ FILLED)."""
    latest: dict[str, OrderLifecycleItem] = {}
    for event in events:
        if not event.event_type.value.startswith("order."):
            continue
        client_id = str(
            event.payload.get("client_order_id")
            or event.payload.get("intent_id")
            or event.event_id
        )
        state = str(event.payload.get("state") or event.event_type.value.removeprefix("order."))
        if state == "intent_created":
            state = "CREATED"
        elif state == "reconciliation_required":
            state = str(event.payload.get("state") or "RECONCILIATION_REQUIRED")
        elif state == "partially_filled":
            state = "PARTIALLY_FILLED"
        elif state == "accepted":
            state = "ACCEPTED"
        elif state == "filled":
            state = "FILLED"
        elif state == "canceled":
            state = "CANCELED"
        item = OrderLifecycleItem(
            client_order_id=client_id,
            state=state,
            side=str(event.payload["side"]) if event.payload.get("side") else None,
            qty=str(event.payload["qty"]) if event.payload.get("qty") else None,
            filled_qty=str(event.payload["filled_qty"]) if event.payload.get("filled_qty") is not None else None,
            correlation_id=event.correlation_id,
            updated_at=event.occurred_at,
            sample=False,
        )
        prev = latest.get(client_id)
        if prev is None or (prev.updated_at or event.occurred_at) <= event.occurred_at:
            # Prefer higher fill progress when timestamps tie.
            if prev is not None and prev.updated_at == event.occurred_at:
                if _order_rank(prev.state) > _order_rank(state):
                    continue
            latest[client_id] = item
    return list(latest.values())


def _order_rank(state: str) -> int:
    order = {
        "CREATED": 1,
        "SUBMISSION_PENDING": 2,
        "ACCEPTED": 3,
        "PARTIALLY_FILLED": 4,
        "FILLED": 5,
        "CANCELED": 5,
        "REJECTED": 5,
        "UNKNOWN": 2,
        "RECONCILIATION_REQUIRED": 2,
    }
    return order.get(state.upper(), 0)


def _row_to_event(row: ObservationEventRow) -> ObservabilityEvent:
    payload = row.payload_json if isinstance(row.payload_json, dict) else {}
    return ObservabilityEvent(
        schema_version=SCHEMA_VERSION,
        event_id=row.event_id,
        event_type=row.event_type,
        occurred_at=_parse_dt(row.occurred_at) or _utc_now(),
        correlation_id=row.correlation_id,
        env_scope=row.env_scope,
        account_scope_label=row.account_scope_label,
        symbol=row.symbol,
        interval=row.interval,
        execution_mode=row.execution_mode,
        pipeline_step=row.pipeline_step,
        message=row.message,
        payload=payload,
    )
