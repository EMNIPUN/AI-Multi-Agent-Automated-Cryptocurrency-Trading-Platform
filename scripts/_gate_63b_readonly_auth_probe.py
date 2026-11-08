"""Gate 63B RO probe: auth schema ACL + Alembic baseline. No mutations."""

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
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("server_version", c.execute(text("SHOW server_version")).scalar())
        print(
            "alembic",
            c.execute(text("SELECT version_num FROM app.alembic_version")).scalar(),
        )
        print(
            "auth_owner",
            c.execute(
                text(
                    "SELECT pg_get_userbyid(n.nspowner) FROM pg_namespace n "
                    "WHERE nspname='auth'"
                )
            ).scalar(),
        )
        print(
            "auth_nspacl",
            c.execute(
                text("SELECT nspacl::text FROM pg_namespace WHERE nspname='auth'")
            ).scalar(),
        )
        print(
            "runtime_usage_auth",
            c.execute(
                text(
                    "SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE')"
                )
            ).scalar(),
        )
        print(
            "runtime_exec_uid",
            c.execute(
                text(
                    "SELECT has_function_privilege("
                    "'cryptonova_api_runtime','auth.uid()','EXECUTE')"
                )
            ).scalar(),
        )
        print(
            "postgres_usage_auth",
            c.execute(
                text("SELECT has_schema_privilege('postgres','auth','USAGE')")
            ).scalar(),
        )
        print(
            "postgres_rolsuper",
            c.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname='postgres'")
            ).scalar(),
        )
        # Can postgres grant on auth? ACL shows USAGE without GRANT OPTION.
        print(
            "postgres_acl_item",
            c.execute(
                text(
                    """
                    SELECT privilege_type, is_grantable
                    FROM aclexplode(
                      (SELECT nspacl FROM pg_namespace WHERE nspname='auth')
                    ) AS a
                    JOIN pg_roles r ON r.oid = a.grantee
                    WHERE r.rolname = 'postgres'
                    """
                )
            ).fetchall(),
        )
        print(
            "note",
            "auth_owner=supabase_admin; postgres USAGE without GRANT OPTION → "
            "future GRANT USAGE needs supabase_admin / dashboard SQL path",
        )
        print(
            "cryptonova_count",
            c.execute(
                text("SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'cryptonova_%'")
            ).scalar(),
        )
        print(
            "login_exists",
            c.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='cryptonova_api_login')"
                )
            ).scalar(),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
