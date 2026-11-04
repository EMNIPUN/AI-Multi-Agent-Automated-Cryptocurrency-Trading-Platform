"""Explicit SAMPLE fixtures for Phase 3A Command Center (offline / labeled)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

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
    PaperWorkspaceSnapshot,
    PipelineStep,
    SignalMarker,
)


def _utc(minutes_ago: float = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)


def build_fixture_events(*, base: datetime | None = None) -> list[ObservabilityEvent]:
    t0 = base or _utc(12)
    corr = f"corr-sample-{t0.strftime('%Y%m%d%H%M')}"
    seq: list[tuple[ObservabilityEventType, PipelineStep, str, dict]] = [
        (
            ObservabilityEventType.AGENT_HEARTBEAT,
            PipelineStep.MARKET_DATA,
            "Worker heartbeat (sample)",
            {"status": "RUNNING", "poll_seconds": 15},
        ),
        (
            ObservabilityEventType.MARKET_CANDLE_CONFIRMED,
            PipelineStep.CONFIRMED_CANDLE,
            "Confirmed candle accepted",
            {"close": 67250.5, "close_ms": int(t0.timestamp() * 1000)},
        ),
        (
            ObservabilityEventType.ANALYSIS_COMPLETED,
            PipelineStep.STRATEGY,
            "EMA/RSI analysis complete",
            {"ema_fast": 67110.2, "ema_slow": 66840.8, "rsi": 54.3},
        ),
        (
            ObservabilityEventType.SIGNAL_GENERATED,
            PipelineStep.SIGNAL,
            "Signal HOLD (sample)",
            {"action": "HOLD", "reason": "rsi_mid_range_sample"},
        ),
        (
            ObservabilityEventType.RISK_BLOCKED,
            PipelineStep.BLOCKED,
            "Risk blocked new exposure (sample)",
            {"verdict": "BLOCKED", "reasons": ["dry_run_fixture_no_live_orders"]},
        ),
        (
            ObservabilityEventType.ORDER_INTENT_CREATED,
            PipelineStep.INTENT,
            "Dry-run intent recorded (sample)",
            {"client_order_id": "sample-intent-001", "state": "DRY_RUN"},
        ),
        (
            ObservabilityEventType.ORDER_RECONCILIATION_REQUIRED,
            PipelineStep.RECONCILIATION,
            "Reconciliation placeholder (sample)",
            {"state": "ACCEPTED", "note": "no exchange contact in fixture"},
        ),
    ]
    events: list[ObservabilityEvent] = []
    for i, (etype, step, msg, payload) in enumerate(seq):
        events.append(
            ObservabilityEvent(
                schema_version=SCHEMA_VERSION,
                event_id=f"evt-sample-{i:04d}-{uuid4().hex[:8]}",
                event_type=etype,
                occurred_at=t0 + timedelta(seconds=i * 8),
                correlation_id=corr,
                env_scope="fixture",
                account_scope_label="sample-account",
                symbol="BTCUSDT",
                interval="15",
                execution_mode=ExecutionMode.DRY_RUN,
                pipeline_step=step,
                message=msg,
                payload=payload,
            )
        )
    return events


def build_sample_candles(n: int = 48) -> list[CandleBar]:
    now = int(_utc().timestamp())
    # Align to 15m bars
    step = 15 * 60
    end = now - (now % step) - step
    bars: list[CandleBar] = []
    price = 67000.0
    for i in range(n):
        t = end - (n - 1 - i) * step
        o = price
        c = price + ((i % 5) - 2) * 35.0
        h = max(o, c) + 40
        l = min(o, c) - 40
        bars.append(
            CandleBar(time=t, open=o, high=h, low=l, close=c, volume=120.0 + i)
        )
        price = c
    return bars


def build_agent_fixture_snapshot() -> AgentSnapshot:
    events = build_fixture_events()
    candles = build_sample_candles()
    last_bar = candles[-1] if candles else None
    heartbeat = _utc(0.2)
    return AgentSnapshot(
        data_mode=DataMode.FIXTURE,
        sample_label="SAMPLE",
        generated_at=_utc(),
        agent_status=AgentRuntimeStatus.IDLE,
        heartbeat_at=heartbeat,
        heartbeat_stale=True,
        stale_after_seconds=30,
        symbol="BTCUSDT",
        interval="15",
        execution_mode=ExecutionMode.DRY_RUN,
        money_view="paper",
        last_confirmed_candle_at=(
            datetime.fromtimestamp(last_bar.time, tz=timezone.utc) if last_bar else None
        ),
        ema_fast=67110.2,
        ema_slow=66840.8,
        rsi=54.3,
        signal_action="HOLD",
        signal_reason="rsi_mid_range_sample",
        risk_verdict="BLOCKED",
        risk_reasons=["dry_run_fixture_no_live_orders", "PRIVATE_DATA_READS_ENABLED=false"],
        current_pipeline_step=PipelineStep.BLOCKED,
        pipeline_blocked=True,
        pipeline_block_reason="Fixture mode — worker not connected; no live Bybit activity",
        candles=candles,
        markers=[
            SignalMarker(
                time=candles[-3].time if len(candles) >= 3 else candles[-1].time,
                action="HOLD",
                price=candles[-3].close if len(candles) >= 3 else candles[-1].close,
                label="SAMPLE HOLD",
                sample=True,
            )
        ],
        orders=[
            OrderLifecycleItem(
                client_order_id="sample-intent-001",
                state="DRY_RUN",
                side="Buy",
                qty="0.001",
                filled_qty="0",
                correlation_id=events[0].correlation_id,
                updated_at=_utc(5),
                sample=True,
            )
        ],
        events=events,
        cursor=events[-1].event_id if events else None,
        notes=[
            "All values are SAMPLE fixtures for Phase 3A UI development.",
            "Worker is not running; chart and timeline are not live market activity.",
            "No Bybit orders are placed from this dashboard.",
            "Live private streams stay disabled until ownership migration is applied.",
        ],
    )


def build_paper_fixture_snapshot() -> PaperWorkspaceSnapshot:
    return PaperWorkspaceSnapshot(
        data_mode=DataMode.FIXTURE,
        sample_label="SAMPLE",
        generated_at=_utc(),
        virtual_equity=10_000.0,
        cash=9_420.55,
        unrealized_pnl=42.10,
        realized_pnl=-18.25,
        positions=[
            {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "qty": "0.01",
                "entry": 66800.0,
                "mark": 67220.0,
                "sl": 66100.0,
                "tp": 68500.0,
                "sample": True,
            }
        ],
        simulated_orders=[
            {
                "id": "paper-ord-001",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "qty": "0.01",
                "state": "FILLED",
                "sample": True,
            }
        ],
        history=[
            {
                "ts": _utc(90).isoformat(),
                "action": "BUY",
                "symbol": "BTCUSDT",
                "pnl": -18.25,
                "sample": True,
            }
        ],
        submit_controls_enabled=False,
        broker_implemented=False,
        notes=[
            "Paper workspace is SAMPLE-only in Phase 3A.",
            "No persistent Python paper broker yet — submit controls stay disabled.",
            "Simulated orders never touch Bybit.",
        ],
    )
