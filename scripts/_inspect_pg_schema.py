"""One-shot schema inspect (no secrets printed)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text

from apps.api.app.config import clear_settings_cache, get_api_settings

clear_settings_cache()
url = get_api_settings().sqlalchemy_url()
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    schemas = conn.execute(
        text(
            "select schema_name from information_schema.schemata "
            "where schema_name not in ('pg_catalog','information_schema','pg_toast') "
            "order by 1"
        )
    ).fetchall()
    print("schemas", [s[0] for s in schemas])
    tabs = conn.execute(
        text(
            "select table_schema || '.' || table_name from information_schema.tables "
            "where table_type='BASE TABLE' and table_schema not in "
            "('pg_catalog','information_schema') order by 1"
        )
    ).fetchall()
    print("table_count", len(tabs))
    print("tables", [t[0] for t in tabs])
    try:
        ver = conn.execute(
            text("select version_num from app.alembic_version")
        ).fetchall()
        print("alembic_app", [r[0] for r in ver])
    except Exception as exc:
        print("alembic_app", type(exc).__name__, str(exc).split("\n")[0][:120])
