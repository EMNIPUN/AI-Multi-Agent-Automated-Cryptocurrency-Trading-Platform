"""FastAPI WebSocket endpoint for public market fan-out (browser ↔ local API)."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.api.app.market_data.stream_hub import get_market_stream_hub

logger = logging.getLogger(__name__)

router = APIRouter(tags=["market-public-ws"])


def _reject_upstream_url_fields(payload: dict[str, Any]) -> str | None:
    banned = ("url", "upstream", "ws_url", "endpoint", "host", "wss")
    for key in payload:
        lowered = str(key).lower()
        if any(b in lowered for b in banned):
            return "upstream_url_fields_forbidden"
    return None


@router.websocket("/api/v1/market/stream")
async def market_public_stream(websocket: WebSocket) -> None:
    """
    Public market stream for local personal-use browsers.

    Protocol (JSON text frames):
      client → {"op":"subscribe","category":"linear","symbols":["BTCUSDT"],"interval":"15"}
      client → {"op":"ping"}
      server → {"type":"status"|ticker|kline|orderbook|trade|...}
      server → {"op":"pong"} / {"type":"error","reason":"..."}

    No Authorization required (public data). Does not expose wallet/private routes.
    """
    await websocket.accept()
    hub = get_market_stream_hub()
    client_id = str(uuid.uuid4())
    loop = asyncio.get_running_loop()
    try:
        client = hub.register_client(client_id, loop)
    except RuntimeError:
        await websocket.send_json(
            {"type": "error", "reason": "too_many_browser_clients"}
        )
        await websocket.close(code=1013)
        return

    await websocket.send_json(
        {
            "type": "hello",
            "client_id": client_id,
            "note": "Public Bybit market stream only — not private wallet/trading.",
            "private_reads_enabled": False,
            "trading_enabled": False,
        }
    )

    async def _reader() -> None:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "reason": "invalid_json"}
                )
                continue
            if not isinstance(msg, dict):
                await websocket.send_json(
                    {"type": "error", "reason": "invalid_message"}
                )
                continue
            banned = _reject_upstream_url_fields(msg)
            if banned:
                await websocket.send_json({"type": "error", "reason": banned})
                continue
            op = msg.get("op")
            if op == "ping":
                await websocket.send_json({"op": "pong"})
                continue
            if op == "subscribe":
                try:
                    symbols = msg.get("symbols") or []
                    if isinstance(symbols, str):
                        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
                    if not isinstance(symbols, list):
                        raise ValueError("invalid_symbols")
                    sub = hub.validate_subscribe(
                        category=str(msg.get("category") or "linear"),
                        symbols=[str(s) for s in symbols],
                        interval=str(msg.get("interval") or "15"),
                    )
                    hub.subscribe_client(client_id, sub)
                    await websocket.send_json(
                        {
                            "type": "subscribed",
                            "category": sub.category.value,
                            "symbols": sorted(sub.symbols),
                            "interval": sub.interval,
                            "stream_mode": "public_ws",
                        }
                    )
                except Exception as exc:  # noqa: BLE001
                    await websocket.send_json(
                        {
                            "type": "error",
                            "reason": str(exc) or type(exc).__name__,
                        }
                    )
                continue
            await websocket.send_json(
                {"type": "error", "reason": "unsupported_op"}
            )

    async def _writer() -> None:
        while True:
            event = await client.queue.get()
            await websocket.send_json(event)

    reader_task = asyncio.create_task(_reader())
    writer_task = asyncio.create_task(_writer())
    try:
        done, pending = await asyncio.wait(
            {reader_task, writer_task},
            return_when=asyncio.FIRST_EXCEPTION,
        )
        for task in pending:
            task.cancel()
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, (WebSocketDisconnect, asyncio.CancelledError)):
                logger.debug("market_stream_task_end err=%s", type(exc).__name__)
    except WebSocketDisconnect:
        pass
    finally:
        reader_task.cancel()
        writer_task.cancel()
        hub.unregister_client(client_id)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
