"""
Append-only worker telemetry ledger.

This file is not the execution, fill, or risk source of truth.
Writes never raise to the caller of ``safe_record``.
Payloads are sanitized before insert. Account fingerprints are not stored.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apps.api.app.observability.types import (
    SCHEMA_VERSION,
    AgentRuntimeStatus,
    AgentSnapshot,
    DataMode,
    ExecutionMode,
    ObservabilityEvent,
    ObservabilityEventType,
    OrderLifecycleItem,
    PipelineStep,
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
    execution_mode: ExecutionMode = ExecutionMode.DRY_RUN,
    pipeline_step: PipelineStep | None = None,
    payload: dict | None = None,
) -> ObservabilityEvent:
    return ObservabilityEvent(
        event_id=event_id,
        event_type=event_type,
        occurred_at=_utc_now(),
        correlation_id=correlation_id,
        env_scope=env_scope,
        account_scope_label="operator-local",
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS observation_events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    correlation_id TEXT,
                    env_scope TEXT NOT NULL,
                    account_scope_label TEXT,
                    symbol TEXT,
                    interval TEXT,
                    execution_mode TEXT NOT NULL,
                    pipeline_step TEXT,
                    message TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )

    def record(self, event: ObservabilityEvent) -> bool:
        payload = sanitize_public_json(event.payload)
        if not isinstance(payload, dict):
            payload = {}
        body = event.model_copy(update={"payload": payload, "account_scope_label": _scope_label(event)})
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO observation_events (
                    event_id, event_type, occurred_at, correlation_id, env_scope,
                    account_scope_label, symbol, interval, execution_mode,
                    pipeline_step, message, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    body.event_id,
                    body.event_type.value,
                    body.occurred_at.astimezone(timezone.utc).isoformat(),
                    body.correlation_id,
                    body.env_scope,
                    body.account_scope_label,
                    body.symbol,
                    body.interval,
                    body.execution_mode.value,
                    body.pipeline_step.value if body.pipeline_step else None,
                    body.message[:500],
                    json.dumps(body.payload, separators=(",", ":"), default=str),
                ),
            )
            inserted = cur.rowcount == 1
            if inserted:
                self._trim(conn)
            return inserted

    def safe_record(self, event: ObservabilityEvent) -> bool:
        try:
            return self.record(event)
        except Exception:
            return False

    def _trim(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            DELETE FROM observation_events
            WHERE seq NOT IN (
                SELECT seq FROM observation_events ORDER BY seq DESC LIMIT ?
            )
            """,
            (self.max_rows,),
        )

    def count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM observation_events").fetchone()
            return int(row["n"])

    def since(self, cursor: str | None, *, limit: int = 200) -> list[ObservabilityEvent]:
        limit = max(1, min(limit, 500))
        sql = "SELECT * FROM observation_events"
        params: list[object] = []
        if cursor and cursor.isdigit():
            sql += " WHERE seq > ?"
            params.append(int(cursor))
        sql += " ORDER BY seq ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_event(row) for row in rows]

    def latest_cursor(self) -> str | None:
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(seq) AS seq FROM observation_events").fetchone()
        if row is None or row["seq"] is None:
            return None
        return str(row["seq"])

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
            candles=[],
            markers=[],
            orders=orders,
            events=events,
            cursor=self.latest_cursor(),
            notes=[
                "Worker telemetry ledger. Not exchange authority.",
                "HOLD is a signal, not a trade.",
                "ACCEPTED is not FILLED.",
                "No candle series is copied into this snapshot.",
            ],
        )

    def _last_of_type(self, kind: ObservabilityEventType) -> ObservabilityEvent | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM observation_events
                WHERE event_type = ?
                ORDER BY seq DESC LIMIT 1
                """,
                (kind.value,),
            ).fetchone()
        return _row_to_event(row) if row else None

    def _newest(self, limit: int) -> list[ObservabilityEvent]:
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM observation_events ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_event(row) for row in reversed(rows)]


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


def _scope_label(event: ObservabilityEvent) -> str | None:
    label = event.account_scope_label or "operator-local"
    lowered = label.lower()
    if "fp" in lowered or len(label) > 32:
        return "operator-local"
    return label


def _last(events: list[ObservabilityEvent], kind: ObservabilityEventType) -> ObservabilityEvent | None:
    found = [e for e in events if e.event_type is kind]
    return found[-1] if found else None


def _num(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


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


def _row_to_event(row: sqlite3.Row) -> ObservabilityEvent:
    payload = json.loads(row["payload_json"] or "{}")
    if not isinstance(payload, dict):
        payload = {}
    return ObservabilityEvent(
        schema_version=SCHEMA_VERSION,
        event_id=row["event_id"],
        event_type=row["event_type"],
        occurred_at=_parse_dt(row["occurred_at"]) or _utc_now(),
        correlation_id=row["correlation_id"],
        env_scope=row["env_scope"],
        account_scope_label=row["account_scope_label"],
        symbol=row["symbol"],
        interval=row["interval"],
        execution_mode=row["execution_mode"],
        pipeline_step=row["pipeline_step"],
        message=row["message"],
        payload=payload,
    )
