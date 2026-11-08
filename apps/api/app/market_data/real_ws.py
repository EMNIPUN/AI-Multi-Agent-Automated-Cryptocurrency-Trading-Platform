"""Real Bybit public WebSocket transport (sync), injectable for the manager."""

from __future__ import annotations

from typing import Any

from websockets.sync.client import connect as ws_connect


class RealBybitPublicSocket:
    """Thin adapter around websockets.sync ClientConnection."""

    def __init__(self, url: str, *, open_timeout: float = 15.0) -> None:
        self._conn = ws_connect(
            url,
            open_timeout=open_timeout,
            close_timeout=2.0,
            max_size=2_000_000,
        )

    def send(self, data: str) -> None:
        self._conn.send(data)

    def recv(self, timeout: float | None = None) -> str:
        raw: Any = self._conn.recv(timeout=timeout)
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass


def connect_bybit_public(url: str) -> RealBybitPublicSocket:
    """
    Connect only to the provided URL.

    Callers must pass allowlisted Bybit public endpoints from ws_url_for_category —
    never browser-supplied URLs.
    """
    if not url.startswith("wss://stream.bybit.com/"):
        raise ValueError("upstream_url_not_allowlisted")
    return RealBybitPublicSocket(url)
