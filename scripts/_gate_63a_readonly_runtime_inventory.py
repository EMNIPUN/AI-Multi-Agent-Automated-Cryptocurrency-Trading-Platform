"""Gate 63A read-only remote inventory. SELECT/catalog only. No DDL/DML."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref

EXPECTED_REF = "wmirifmgaftassgrfbyl"
EXPECTED_REV = "20261108_0005"
EXPECTED_SHA = "9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a"
PHASE4D = (
    "signal_history",
    "signal_agent_contributions",
    "signal_risk_events",
    "scheduler_evaluation_history",
    "scheduler_audit",
)


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    mig = ROOT / "apps/api/alembic/versions/20261108_0005_option_a_least_privilege.py"
    digest = hashlib.sha256(mig.read_bytes()).hexdigest() if mig.exists() else "missing"
    print("migration_0005_sha256", digest)
    print("checksum_match", digest == EXPECTED_SHA)

    env_text = (ROOT / ".env").read_text(encoding="utf-8", errors="replace")
    for key in (
        "RUNTIME_DB_IDENTITY_ENABLED",
        "SIGNAL_SUPABASE_WRITES_ENABLED",
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
        "SIGNAL_CLOUD_SYNC_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_ENABLED",
        "AGENT_ALLOW_LIVE",
        "TESTNET_ORDER_SUBMISSION_APPROVED",
        "PERPETUAL_AUTO_EXECUTION_ENABLED",
        "CRYPTONOVA_ALLOW_DEV_MIGRATIONS",
        "PRIVATE_DATA_READS_ENABLED",
    ):
        m = re.search(rf"^{key}=(.*)$", env_text, re.M)
        print(f"ENV {key}={(m.group(1).strip() if m else '<unset>')}")

    raw = os.environ.get("DATABASE_URL") or ""
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    print("db_host", info.host)
    print("db_user", info.user)
    print("db_ref", ref)
    print("db_ref_match", ref == EXPECTED_REF)
    print("db_region_ok", "ap-southeast-2" in (info.host or ""))
    print("connection_looks_privileged_postgres", "postgres" in (info.user or "").lower())

    eng = create_engine(normalize_database_url(raw), pool_pre_ping=True, future=True)
    with eng.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        print("server_version", c.execute(text("SHOW server_version")).scalar())
        print(
            "alembic",
            c.execute(text("SELECT version_num FROM app.alembic_version")).scalar(),
        )
        print("alembic_match", c.execute(text("SELECT version_num FROM app.alembic_version")).scalar() == EXPECTED_REV)
        print("session_user", c.execute(text("SELECT session_user")).scalar())
        print("current_user", c.execute(text("SELECT current_user")).scalar())
        bypass = c.execute(
            text(
                "SELECT rolbypassrls FROM pg_roles WHERE rolname = session_user"
            )
        ).scalar()
        print("session_user_bypassrls", bypass)

        rows = c.execute(
            text(
                """
                SELECT rolname, rolcanlogin, rolbypassrls, rolsuper, rolinherit,
                       rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname IN (
                  'cryptonova_api_runtime', 'cryptonova_migrator',
                  'cryptonova_api_login', 'postgres', 'authenticated'
                )
                ORDER BY rolname
                """
            )
        ).fetchall()
        for r in rows:
            print("role", tuple(r))
        print(
            "cryptonova_count",
            c.execute(
                text("SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'cryptonova_%'")
            ).scalar(),
        )
        print(
            "login_role_exists",
            c.execute(
                text(
                    "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='cryptonova_api_login')"
                )
            ).scalar(),
        )

        for t in PHASE4D:
            n = c.execute(text(f'SELECT COUNT(*) FROM app."{t}"')).scalar()
            print("count", t, int(n or 0))

        owners = c.execute(
            text(
                """
                SELECT c.relname, pg_get_userbyid(c.relowner)
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'app' AND c.relkind = 'r'
                ORDER BY 1
                """
            )
        ).fetchall()
        for o in owners:
            print("owner", o[0], o[1])

        grants = c.execute(
            text(
                """
                SELECT table_name, privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema = 'app' AND grantee = 'cryptonova_api_runtime'
                ORDER BY table_name, privilege_type
                """
            )
        ).fetchall()
        for g in grants:
            print("runtime_grant", g[0], g[1])

        dels = c.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.role_table_grants
                WHERE table_schema = 'app'
                  AND grantee = 'cryptonova_api_runtime'
                  AND privilege_type = 'DELETE'
                """
            )
        ).fetchall()
        print("runtime_delete_grants", [d[0] for d in dels])

        print(
            "runtime_create_app",
            c.execute(
                text("SELECT has_schema_privilege('cryptonova_api_runtime','app','CREATE')")
            ).scalar(),
        )
        print(
            "runtime_usage_app",
            c.execute(
                text("SELECT has_schema_privilege('cryptonova_api_runtime','app','USAGE')")
            ).scalar(),
        )
        print(
            "runtime_usage_auth",
            c.execute(
                text("SELECT has_schema_privilege('cryptonova_api_runtime','auth','USAGE')")
            ).scalar(),
        )
        print(
            "runtime_exec_uid",
            c.execute(
                text(
                    "SELECT has_function_privilege('cryptonova_api_runtime','auth.uid()','EXECUTE')"
                )
            ).scalar(),
        )
        print(
            "migrator_create_app",
            c.execute(
                text("SELECT has_schema_privilege('cryptonova_migrator','app','CREATE')")
            ).scalar(),
        )

        # Membership edges (login should not exist yet)
        mem = c.execute(
            text(
                """
                SELECT r.rolname AS member, m.rolname AS role, pg_has_role(r.oid, m.oid, 'MEMBER')
                FROM pg_roles r
                CROSS JOIN pg_roles m
                WHERE r.rolname LIKE 'cryptonova_%'
                  AND m.rolname LIKE 'cryptonova_%'
                  AND r.rolname <> m.rolname
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        for row in mem:
            if row[2]:
                print("membership", row[0], "IN", row[1])

        pols = c.execute(
            text(
                """
                SELECT tablename, policyname, roles::text, cmd
                FROM pg_policies
                WHERE schemaname = 'app'
                ORDER BY 1, 2
                """
            )
        ).fetchall()
        for p in pols:
            print("policy", p[0], p[1], p[2], p[3])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
