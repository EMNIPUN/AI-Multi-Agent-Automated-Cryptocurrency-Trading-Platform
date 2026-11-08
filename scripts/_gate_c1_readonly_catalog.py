"""Gate C1 read-only Supabase catalog inspection. SELECT/catalog only. No DDL/DML."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref

# Historical Gate B revision file (integrity only).
EXPECTED_SHA_0004 = "1ea22dc805ff5bb235fec970cec1dd9b120c0daab573b210256d50856c722145"
# Current approved security revision after Gate 62.
EXPECTED_SHA_0005 = "9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a"
EXPECTED_REF = "wmirifmgaftassgrfbyl"
EXPECTED_REV = "20261108_0005"
TABLES = (
    "signal_history",
    "signal_agent_contributions",
    "signal_risk_events",
    "scheduler_evaluation_history",
    "scheduler_audit",
)


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    mig_0004 = ROOT / "apps/api/alembic/versions/20261107_0004_phase4d_signal_persistence.py"
    mig_0005 = ROOT / "apps/api/alembic/versions/20261108_0005_option_a_least_privilege.py"
    digest_0004 = (
        hashlib.sha256(mig_0004.read_bytes()).hexdigest() if mig_0004.exists() else "missing"
    )
    digest_0005 = (
        hashlib.sha256(mig_0005.read_bytes()).hexdigest() if mig_0005.exists() else "missing"
    )
    print("migration_0004_sha256", digest_0004)
    print("checksum_0004_match", digest_0004 == EXPECTED_SHA_0004)
    print("migration_0005_sha256", digest_0005)
    print("checksum_0005_match", digest_0005 == EXPECTED_SHA_0005)
    print("expected_remote_alembic", EXPECTED_REV)

    env_text = (ROOT / ".env").read_text(encoding="utf-8", errors="replace")
    for key in (
        "SIGNAL_SUPABASE_WRITES_ENABLED",
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
        "SIGNAL_CLOUD_SYNC_ENABLED",
        "SIGNAL_CLOUD_OWNER_USER_ID",
        "EXCHANGE_BINDING_PERSISTENCE_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED",
        "AGENT_ALLOW_LIVE",
        "TESTNET_ORDER_SUBMISSION_APPROVED",
        "PERPETUAL_AUTO_EXECUTION_ENABLED",
        "CRYPTONOVA_ALLOW_DEV_MIGRATIONS",
        "PRIVATE_DATA_READS_ENABLED",
        "RUNTIME_DB_IDENTITY_ENABLED",
    ):
        m = re.search(rf"^{key}=(.*)$", env_text, re.M)
        print(f"ENV {key}={(m.group(1).strip() if m else '<unset>')}")

    raw = os.environ.get("DATABASE_URL") or ""
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    print("db_host", info.host)
    print("db_ref", ref)
    print("db_ref_match", ref == EXPECTED_REF)
    print("db_region_ok", "ap-southeast-2" in (info.host or ""))

    sqlite_path = ROOT / "data" / "multi_agent_signals.sqlite3"
    conn = sqlite3.connect(f"file:{sqlite_path.as_posix()}?mode=ro", uri=True)
    try:
        print(
            "sqlite_schema",
            conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0],
        )
        print("sqlite_integrity", conn.execute("PRAGMA integrity_check").fetchone()[0])
        for t in (
            "signal_history",
            "paper_risk_state",
            "cloud_sync_outbox",
            "evaluation_checkpoints",
        ):
            print(f"sqlite_{t}", conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    finally:
        conn.close()
    bak = ROOT / "data/backups/multi_agent_signals_20261107_202853.sqlite3"
    print("backup_exists", bak.exists())

    url = normalize_database_url(raw, require_ssl_for_remote=True)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as c:
        # Explicitly read-only transaction
        c.execute(text("SET TRANSACTION READ ONLY"))
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        print("remote_alembic", rev)
        print("remote_alembic_match", rev == EXPECTED_REV)

        role = c.execute(text("SELECT current_user, session_user")).fetchone()
        print("db_current_user", role[0])
        print("db_session_user", role[1])
        attrs = c.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcanlogin "
                "FROM pg_roles WHERE rolname = current_user"
            )
        ).fetchone()
        if attrs:
            print("rolsuper", bool(attrs[0]))
            print("rolbypassrls", bool(attrs[1]))
            print("rolcanlogin", bool(attrs[2]))

        for table in TABLES:
            exists = c.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='app' AND table_name=:t"
                ),
                {"t": table},
            ).scalar()
            print(f"table_{table}_exists", bool(exists))
            if not exists:
                continue
            n = c.execute(text(f'SELECT COUNT(*) FROM app."{table}"')).scalar()
            print(f"count_{table}", int(n or 0))
            cols = c.execute(
                text(
                    "SELECT column_name, data_type, is_nullable "
                    "FROM information_schema.columns "
                    "WHERE table_schema='app' AND table_name=:t "
                    "ORDER BY ordinal_position"
                ),
                {"t": table},
            ).fetchall()
            print(
                f"columns_{table}",
                [(a, b, cnull) for a, b, cnull in cols],
            )
            rls = c.execute(
                text(
                    "SELECT c.relrowsecurity, c.relforcerowsecurity "
                    "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='app' AND c.relname=:t"
                ),
                {"t": table},
            ).fetchone()
            print(f"rls_{table}", bool(rls[0]) if rls else None, "force", bool(rls[1]) if rls else None)
            pols = c.execute(
                text(
                    "SELECT pol.polname, pol.polcmd::text "
                    "FROM pg_policy pol "
                    "JOIN pg_class c ON c.oid=pol.polrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='app' AND c.relname=:t"
                ),
                {"t": table},
            ).fetchall()
            print(f"policies_{table}", [(p[0], p[1]) for p in pols])
            cons = c.execute(
                text(
                    "SELECT con.conname, con.contype::text "
                    "FROM pg_constraint con "
                    "JOIN pg_class c ON c.oid=con.conrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE n.nspname='app' AND c.relname=:t "
                    "ORDER BY 1"
                ),
                {"t": table},
            ).fetchall()
            print(f"constraints_{table}", [(x[0], x[1]) for x in cons])
            idxs = c.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname='app' AND tablename=:t ORDER BY 1"
                ),
                {"t": table},
            ).fetchall()
            print(f"indexes_{table}", [x[0] for x in idxs])
            grants = c.execute(
                text(
                    "SELECT grantee, privilege_type "
                    "FROM information_schema.role_table_grants "
                    "WHERE table_schema='app' AND table_name=:t "
                    "ORDER BY 1,2"
                ),
                {"t": table},
            ).fetchall()
            # redact nothing sensitive; role names ok
            print(f"grants_{table}", [(g[0], g[1]) for g in grants])
        c.rollback()
    ok = (
        ref == EXPECTED_REF
        and digest_0005 == EXPECTED_SHA_0005
        and rev == EXPECTED_REV
    )
    print("catalog_exit_ok", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
