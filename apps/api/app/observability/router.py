"""
Read-only observability HTTP contracts.

Fixture mode: labeled SAMPLE snapshots (no private tenant data).
Live SSE: disabled until ownership migration + PRIVATE_DATA_READS_ENABLED.
No trading / agent start-stop / order mutation routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from apps.api.app.auth.principal import AuthenticatedPrincipal
from apps.api.app.config import ApiSettings, get_api_settings
from apps.api.app.deps import get_current_principal
from apps.api.app.observability.fixtures import (
    build_agent_fixture_snapshot,
    build_paper_fixture_snapshot,
)
from apps.api.app.observability.types import (
    AgentSnapshot,
    ObservabilityStreamStatus,
    PaperWorkspaceSnapshot,
)


def _worker_snapshot_response(settings: ApiSettings):
    from agent.telemetry_ledger import TelemetryLedger, unavailable_snapshot

    path = (settings.observability_ledger_path or "").strip()
    if not path:
        return unavailable_snapshot("Worker ledger is not configured.")
    ledger_path = path
    from pathlib import Path

    if not Path(ledger_path).is_file():
        return unavailable_snapshot("Worker ledger has no file yet. No heartbeat was invented.")
    ledger = TelemetryLedger(ledger_path)
    if ledger.count() == 0:
        snap = unavailable_snapshot("Worker ledger is empty. Agent status is UNKNOWN.")
        return snap
    return ledger.snapshot()


router = APIRouter(prefix="/api/v1/observability", tags=["observability"])


def _filter_snapshot_for_binding(snap: AgentSnapshot, telemetry_scope_id: str) -> AgentSnapshot:
    """Fail closed: only events/markers evidenced for the verified telemetry scope."""
    from agent.telemetry_ledger import unavailable_snapshot

    events = [
        e
        for e in snap.events
        if (e.account_scope_label or "") == telemetry_scope_id
    ]
    if not events:
        return unavailable_snapshot(
            "No telemetry events for the authorized exchange-account binding."
        )
    # Do not leak unscoped chart markers / orders from other tenants.
    scoped_signal_times = {
        int(e.payload["candle_start_ms"]) // 1000
        for e in events
        if str(getattr(e.event_type, "value", e.event_type)) == "signal.generated"
        and isinstance(e.payload.get("candle_start_ms"), (int, float))
    }
    markers = [m for m in snap.markers if m.time in scoped_signal_times] if scoped_signal_times else []
    return snap.model_copy(
        update={
            "events": events,
            "markers": markers,
            "orders": [],  # order table is operator ledger; ownership-bound order reads come later
            "notes": list(snap.notes)
            + ["Filtered to authorized exchange-account telemetry scope."],
        }
    )


@router.get("/worker-snapshot", response_model=AgentSnapshot)
def worker_snapshot(
    request: Request,
    settings: ApiSettings = Depends(get_api_settings),
    cursor: str | None = Query(default=None, max_length=32),
) -> AgentSnapshot:
    """
    Worker telemetry snapshot.

    Access modes:
    - Operator-local diagnostic (no Authorization, loopback peer only).
    - Owner-bound authenticated read (JWT + active binding + PRIVATE_DATA_READS)
      filtered to that binding's telemetry_scope_id.

    Does not serve SAMPLE fixtures. SSE stays disabled.
    Client-supplied account IDs are not accepted as ownership proof.
    """
    from apps.api.app.exchange.access import ExchangeReadMode, resolve_exchange_read_context

    _ = cursor
    ctx = resolve_exchange_read_context(request, settings)
    snap = _worker_snapshot_response(settings)
    if ctx.mode is ExchangeReadMode.OWNER_BOUND:
        if ctx.binding is None:
            raise HTTPException(status_code=403, detail="exchange_binding_missing")
        return _filter_snapshot_for_binding(snap, ctx.binding.telemetry_scope_id)
    return snap


@router.get("/status", response_model=ObservabilityStreamStatus)
def observability_status(
    settings: ApiSettings = Depends(get_api_settings),
) -> ObservabilityStreamStatus:
    fixture = settings.observability_fixture_mode
    live = (
        settings.observability_live_stream_enabled
        and settings.private_data_reads_enabled
    )
    reason = (
        "fixture_mode"
        if fixture and not live
        else (
            "live_enabled"
            if live
            else "live_stream_disabled_until_ownership_validated"
        )
    )
    return ObservabilityStreamStatus(
        live_stream_enabled=bool(live),
        fixture_mode=bool(fixture),
        reason=reason,
        private_data_reads_enabled=settings.private_data_reads_enabled,
    )


@router.get("/snapshot", response_model=AgentSnapshot)
def agent_snapshot(
    settings: ApiSettings = Depends(get_api_settings),
) -> AgentSnapshot:
    """
    Command-center snapshot.

    Phase 3A: returns explicitly labeled fixtures when fixture mode is on.
    Live private snapshots stay unavailable (503) until ownership + flags.
    """
    if settings.observability_fixture_mode:
        return build_agent_fixture_snapshot()
    if not settings.private_data_reads_enabled:
        raise HTTPException(
            status_code=503,
            detail="observability_live_unavailable",
        )
    raise HTTPException(status_code=503, detail="observability_live_unavailable")


@router.get("/paper/snapshot", response_model=PaperWorkspaceSnapshot)
def paper_snapshot(
    settings: ApiSettings = Depends(get_api_settings),
) -> PaperWorkspaceSnapshot:
    if settings.observability_fixture_mode:
        return build_paper_fixture_snapshot()
    raise HTTPException(status_code=503, detail="paper_broker_unavailable")


@router.get("/stream")
def observability_stream(
    settings: ApiSettings = Depends(get_api_settings),
    cursor: str | None = Query(default=None, max_length=128),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> StreamingResponse:
    """
    Authenticated SSE — disabled until live stream + ownership flags are on.

    Tokens must arrive via Authorization header (or same-origin proxy cookie),
    never as query parameters.
    """
    _ = cursor  # reserved for reconnect catch-up
    _ = principal
    live = (
        settings.observability_live_stream_enabled
        and settings.private_data_reads_enabled
    )
    if not live:
        raise HTTPException(
            status_code=403,
            detail="observability_live_stream_disabled",
        )

    # Placeholder: live fan-out not implemented in Phase 3A.
    raise HTTPException(status_code=503, detail="observability_live_stream_not_wired")
