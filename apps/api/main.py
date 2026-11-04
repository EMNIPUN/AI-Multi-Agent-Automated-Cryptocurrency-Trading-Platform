"""
ASGI entrypoint.

Bind loopback by default:

    uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

Do not apply Alembic migrations from this process. Do not call Bybit.
"""

from __future__ import annotations

from apps.api.app.factory import create_app

app = create_app()
