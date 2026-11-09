"""
ASGI entrypoint.

Bind loopback by default:

    uv run uvicorn apps.api.main:app --host 127.0.0.1 --port 8000

Do not apply Alembic migrations from this process. Do not call Bybit.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Agent/paper code reads SIGNAL_CLOUD_OWNER_USER_ID via os.getenv.
# Pydantic settings alone does not export .env into the process environment.
_ROOT = Path(__file__).resolve().parents[2]
# Prefer repo .env over stale shell/process defaults (live gates, owner id, etc.).
load_dotenv(_ROOT / ".env", override=True)

from apps.api.app.factory import create_app

app = create_app()
