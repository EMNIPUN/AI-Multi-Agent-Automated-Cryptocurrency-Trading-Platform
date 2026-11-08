"""Gate 61 read-only role / auth.uid probe. No DDL/DML."""

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
        print("ABORT unexpected project")
        return 2
    eng = create_engine(normalize_database_url(raw), pool_pre_ping=True, future=True)
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        roles = conn.execute(
            text(
                """
                SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolinherit
                FROM pg_roles
                WHERE rolname = ANY(:names)
                ORDER BY 1
                """
            ),
            {
                "names": [
                    "cryptonova_api_runtime",
                    "cryptonova_migrator",
                    "cryptonova_api_runtime_login",
                    "authenticated",
                    "anon",
                    "postgres",
                    "authenticator",
                ]
            },
        ).fetchall()
        for row in roles:
            print("role", tuple(row))
        count = conn.execute(
            text("SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'cryptonova_%'")
        ).scalar()
        print("cryptonova_role_count", count)
        uid = conn.execute(
            text(
                """
                SELECT n.nspname, p.proname
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'auth' AND p.proname = 'uid'
                """
            )
        ).fetchall()
        print("auth_uid_functions", uid)
        print(
            "postgres_can_execute_auth_uid",
            conn.execute(
                text("SELECT has_function_privilege('postgres', 'auth.uid()', 'EXECUTE')")
            ).scalar(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
