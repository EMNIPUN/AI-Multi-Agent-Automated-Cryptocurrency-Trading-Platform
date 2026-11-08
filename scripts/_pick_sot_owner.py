"""Print first auth.users id for local SoT binding (no secrets beyond uuid)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.config import clear_settings_cache, get_api_settings

load_dotenv(ROOT / ".env")
clear_settings_cache()
engine = create_engine(get_api_settings().sqlalchemy_url(), pool_pre_ping=True)
with engine.connect() as c:
    row = c.execute(text("select id::text from auth.users order by created_at nulls last limit 1")).fetchone()
    print(row[0] if row else "NONE")
