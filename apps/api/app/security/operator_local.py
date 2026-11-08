"""Shared operator-local diagnostic gate (TCP peer, not Host header)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from apps.api.app.config import ApiSettings

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_LOOPBACK_BINDINGS = {"127.0.0.1", "::1", "localhost"}


def assert_operator_local_diagnostic(request: Request, settings: ApiSettings) -> None:
    """
    Fail closed for browser users and proxy-forwarded clients.

    Uses the TCP peer from ASGI (request.client.host), not the Host header.
    Rejects Authorization (no user↔exchange binding) and forwarded headers.
    """
    if request.headers.get("authorization"):
        raise HTTPException(status_code=403, detail="operator_diagnostic_not_bound_to_user")
    if request.headers.get("x-forwarded-for") or request.headers.get("x-real-ip"):
        raise HTTPException(status_code=403, detail="operator_diagnostic_proxy_forward_rejected")
    bind = (settings.api_host or "").strip().lower()
    if bind not in _LOOPBACK_BINDINGS:
        raise HTTPException(status_code=403, detail="operator_diagnostic_bind_not_loopback")
    peer = request.client.host if request.client else ""
    if peer not in _LOOPBACK_HOSTS:
        raise HTTPException(status_code=403, detail="operator_diagnostic_loopback_only")
