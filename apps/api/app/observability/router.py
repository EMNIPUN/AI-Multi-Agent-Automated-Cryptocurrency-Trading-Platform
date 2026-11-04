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


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_LOOPBACK_BINDINGS = {"127.0.0.1", "::1", "localhost"}


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


def _assert_operator_local_diagnostic(request: Request, settings: ApiSettings) -> None:
    """
    Fail closed for browser users and proxy-forwarded clients.

    Uses the TCP peer from ASGI (request.client.host), not the Host header.
    Rejects Authorization (no user↔exchange binding) and forwarded headers
    that would imply the app is behind an untrusted proxy hop.
    """
    if request.headers.get("authorization"):
        raise HTTPException(status_code=403, detail="worker_telemetry_not_bound_to_user")
    if request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip"):
        raise HTTPException(status_code=403, detail="worker_telemetry_proxy_forward_rejected")
    bind = (settings.api_host or "").strip().lower()
    if bind not in _LOOPBACK_BINDINGS:
        raise HTTPException(status_code=403, detail="worker_telemetry_bind_not_loopback")
    peer = request.client.host if request.client else ""
    if peer not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="worker_telemetry_loopback_only")


router = APIRouter(prefix="/api/v1/observability", tags=["observability"])


@router.get("/worker-snapshot", response_model=AgentSnapshot)
def worker_snapshot(
    request: Request,
    settings: ApiSettings = Depends(get_api_settings),
    cursor: str | None = Query(default=None, max_length=32),
) -> AgentSnapshot:
    """
    Operator-local diagnostic snapshot.

    Rejects Authorization and non-loopback peers. Does not serve SAMPLE fixtures.
    SSE stays disabled.
    """
    _ = cursor
    _assert_operator_local_diagnostic(request, settings)
    return _worker_snapshot_response(settings)


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
