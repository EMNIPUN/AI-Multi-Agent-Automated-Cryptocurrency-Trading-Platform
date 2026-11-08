"""Gate 62 read-only: server version + confirm no cryptonova roles. No DDL/DML."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    raw = os.environ.get("DATABASE_URL") or ""
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    print("db_ref", ref)
    if ref != "wmirifmgaftassgrfbyl":
        print("ABORT")
        return 2
    eng = create_engine(normalize_database_url(raw), pool_pre_ping=True, future=True)
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        print("server_version", conn.execute(text("SHOW server_version")).scalar())
        print(
            "cryptonova_roles",
            conn.execute(
                text("SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'cryptonova_%'")
            ).scalar(),
        )
        print(
            "auth_uid_exists",
            conn.execute(
                text(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM pg_proc p
                      JOIN pg_namespace n ON n.oid = p.pronamespace
                      WHERE n.nspname = 'auth' AND p.proname = 'uid'
                    )
                    """
                )
            ).scalar(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
