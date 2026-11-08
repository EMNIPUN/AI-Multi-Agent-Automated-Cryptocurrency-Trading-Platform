"""Option A read-only inventory of app table owners and RLS policies. SELECT only."""

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
    eng = create_engine(
        normalize_database_url(raw), pool_pre_ping=True, future=True
    )
    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        tables = conn.execute(
            text(
                """
                SELECT n.nspname, c.relname,
                       pg_get_userbyid(c.relowner) AS owner,
                       c.relrowsecurity, c.relforcerowsecurity
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'app' AND c.relkind = 'r'
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        for row in tables:
            print(
                "table",
                row[0],
                row[1],
                "owner",
                row[2],
                "rls",
                row[3],
                "force",
                row[4],
            )
        policies = conn.execute(
            text(
                """
                SELECT tablename, policyname, cmd, roles::text, qual, with_check
                FROM pg_policies
                WHERE schemaname = 'app'
                ORDER BY tablename, policyname
                """
            )
        ).fetchall()
        for p in policies:
            print(
                "policy",
                p[0],
                p[1],
                "cmd",
                p[2],
                "roles",
                p[3],
                "using",
                p[4],
                "check",
                p[5],
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
