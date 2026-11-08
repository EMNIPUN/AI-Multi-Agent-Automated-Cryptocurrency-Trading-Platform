"""Gate 63A RO: inspect auth schema ACL / USAGE for runtime role. No mutations."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref
from apps.api.app.database_url import inspect_database_url


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    raw = os.environ.get("DATABASE_URL") or ""
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    if ref != "wmirifmgaftassgrfbyl":
        print("ABORT_wrong_project", ref)
        return 2
    eng = create_engine(normalize_database_url(raw), pool_pre_ping=True, future=True)
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print(
            "auth_nspacl",
            c.execute(
                text("SELECT nspacl::text FROM pg_namespace WHERE nspname='auth'")
            ).scalar(),
        )
        print(
            "has_usage_runtime",
            c.execute(
                text(
                    "SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE')"
                )
            ).scalar(),
        )
        print(
            "has_usage_postgres",
            c.execute(
                text("SELECT has_schema_privilege('postgres','auth','USAGE')")
            ).scalar(),
        )
        print(
            "has_exec_uid_runtime",
            c.execute(
                text(
                    "SELECT has_function_privilege('cryptonova_api_runtime','auth.uid()','EXECUTE')"
                )
            ).scalar(),
        )
        # Privilege grants recorded for auth.uid
        rows = c.execute(
            text(
                """
                SELECT grantee, privilege_type
                FROM information_schema.routine_privileges
                WHERE specific_schema='auth' AND routine_name='uid'
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        for r in rows:
            print("uid_grant", r[0], r[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
