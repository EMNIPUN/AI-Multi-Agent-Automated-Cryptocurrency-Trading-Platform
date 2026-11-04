"""
Typed observability event contracts (Phase 3A).

Safe, browser-facing fields only — never include API keys, JWTs, DSNs, or raw
account fingerprints. schema_version allows forward-compatible clients.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "1.0.0"


class ObservabilityEventType(str, Enum):
    AGENT_STARTED = "agent.started"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_STOPPED = "agent.stopped"
    AGENT_ERROR = "agent.error"
    MARKET_CANDLE_CONFIRMED = "market.candle_confirmed"
    ANALYSIS_COMPLETED = "analysis.completed"
    SIGNAL_GENERATED = "signal.generated"
    RISK_APPROVED = "risk.approved"
    RISK_BLOCKED = "risk.blocked"
    RISK_HALTED = "risk.halted"
    ORDER_INTENT_CREATED = "order.intent_created"
    ORDER_ACCEPTED = "order.accepted"
    ORDER_PARTIALLY_FILLED = "order.partially_filled"
    ORDER_FILLED = "order.filled"
    ORDER_CANCELED = "order.canceled"
    ORDER_RECONCILIATION_REQUIRED = "order.reconciliation_required"
    AGENT_HALTED = "agent.halted"


class ExecutionMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    MAINNET_READONLY = "MAINNET_READONLY"


class AgentRuntimeStatus(str, Enum):
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    OFFLINE = "OFFLINE"
    HALTED = "HALTED"
    UNKNOWN = "UNKNOWN"


class PipelineStep(str, Enum):
    MARKET_DATA = "market_data"
    CONFIRMED_CANDLE = "confirmed_candle"
    STRATEGY = "strategy"
    SIGNAL = "signal"
    RISK = "risk"
    INTENT = "intent"
    RECONCILIATION = "reconciliation"
    POSITION = "position"
    BLOCKED = "blocked"
    HALTED = "halted"
    UNKNOWN = "unknown"


class DataMode(str, Enum):
    FIXTURE = "fixture"
    LIVE = "live"
    UNAVAILABLE = "unavailable"


class ObservabilityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    event_id: str
    event_type: ObservabilityEventType
    occurred_at: datetime
    correlation_id: str | None = None
    env_scope: str = "local"
    # Never raw account fingerprint — optional redacted label only.
    account_scope_label: str | None = None
    owner_user_id: UUID | None = None
    symbol: str | None = None
    interval: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.DRY_RUN
    pipeline_step: PipelineStep | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class CandleBar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: int  # unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class SignalMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time: int
    action: Literal["BUY", "SELL", "HOLD"]
    price: float
    label: str = ""
    sample: bool = True


class OrderLifecycleItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_order_id: str
    state: str
    side: str | None = None
    qty: str | None = None
    filled_qty: str | None = None
    correlation_id: str | None = None
    updated_at: datetime | None = None
    sample: bool = True


class AgentSnapshot(BaseModel):
    """Command-center snapshot — fixtures must set data_mode=fixture."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    data_mode: DataMode
    sample_label: str | None = "SAMPLE"
    generated_at: datetime
    agent_status: AgentRuntimeStatus
    heartbeat_at: datetime | None = None
    heartbeat_stale: bool = True
    stale_after_seconds: int = 30
    symbol: str
    interval: str
    execution_mode: ExecutionMode
    money_view: Literal["paper", "real_readonly"] = "paper"
    last_confirmed_candle_at: datetime | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    rsi: float | None = None
    signal_action: Literal["BUY", "SELL", "HOLD"] | None = None
    signal_reason: str | None = None
    risk_verdict: Literal["APPROVED", "BLOCKED", "UNKNOWN", "N/A"] = "N/A"
    risk_reasons: list[str] = Field(default_factory=list)
    current_pipeline_step: PipelineStep = PipelineStep.UNKNOWN
    pipeline_blocked: bool = False
    pipeline_block_reason: str | None = None
    candles: list[CandleBar] = Field(default_factory=list)
    markers: list[SignalMarker] = Field(default_factory=list)
    orders: list[OrderLifecycleItem] = Field(default_factory=list)
    events: list[ObservabilityEvent] = Field(default_factory=list)
    cursor: str | None = None
    notes: list[str] = Field(default_factory=list)


class PaperWorkspaceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = SCHEMA_VERSION
    data_mode: DataMode = DataMode.FIXTURE
    sample_label: str = "SAMPLE"
    generated_at: datetime
    virtual_equity: float
    cash: float
    unrealized_pnl: float
    realized_pnl: float
    positions: list[dict[str, Any]] = Field(default_factory=list)
    simulated_orders: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    submit_controls_enabled: bool = False
    broker_implemented: bool = False
    notes: list[str] = Field(default_factory=list)


class ObservabilityStreamStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    live_stream_enabled: bool = False
    fixture_mode: bool = True
    reason: str = "ownership_migration_pending"
    private_data_reads_enabled: bool = False
