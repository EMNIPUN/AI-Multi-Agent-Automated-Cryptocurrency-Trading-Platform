"""
Gate B execute 20261107_0004 — requires operator approval already obtained.

Does NOT enable cloud writes/sync/import/orders.
Restores CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false after attempt.
Never prints DATABASE_URL or passwords.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from apps.api.app.database_url import inspect_database_url, normalize_database_url
from scripts.verify_dev_database_target import extract_project_ref, verify_dev_database_target

EXPECTED_SHA = "1ea22dc805ff5bb235fec970cec1dd9b120c0daab573b210256d50856c722145"
EXPECTED_PROJECT = "wmirifmgaftassgrfbyl"
EXPECTED_BEFORE = "20261105_0003"
EXPECTED_AFTER = "20261107_0004"
MIG_NAME = "20261107_0004_phase4d_signal_persistence.py"
BACKUP = ROOT / "data" / "backups" / "multi_agent_signals_20261107_202853.sqlite3"
PROPOSED = ROOT / "apps" / "api" / "alembic" / "versions_proposed" / MIG_NAME
ACTIVE = ROOT / "apps" / "api" / "alembic" / "versions" / MIG_NAME
EXPECTED_TABLES = (
    "signal_history",
    "signal_agent_contributions",
    "signal_risk_events",
    "scheduler_evaluation_history",
    "scheduler_audit",
)
EXISTING_TABLES = (
    "agent_decisions",
    "system_events",
    "strategy_configs",
    "exchange_account_bindings",
)


def _fail(msg: str) -> None:
    print(f"FAIL:{msg}")
    raise SystemExit(2)


def _load_env_file() -> str:
    load_dotenv(ROOT / ".env", override=False)
    return (ROOT / ".env").read_text(encoding="utf-8", errors="replace")


def _gate_off(env_text: str, key: str, *, allow_unset: bool = True) -> None:
    m = re.search(rf"^{key}=(.*)$", env_text, re.M)
    if m is None:
        if allow_unset:
            return
        _fail(f"{key}_missing")
    val = m.group(1).strip().lower()
    if val in {"1", "true", "yes", "on"}:
        _fail(f"{key}_enabled")


def prechecks() -> dict:
    env_text = _load_env_file()
    if not PROPOSED.exists():
        _fail("proposed_migration_missing")
    digest = hashlib.sha256(PROPOSED.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA:
        _fail(f"checksum_mismatch:{digest}")
    if not BACKUP.exists():
        _fail("sqlite_backup_missing")
    conn = sqlite3.connect(f"file:{BACKUP.as_posix()}?mode=ro", uri=True)
    try:
        ik = conn.execute("PRAGMA integrity_check").fetchone()[0]
        ver = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    finally:
        conn.close()
    if ik != "ok" or str(ver) != "4":
        _fail(f"sqlite_backup_invalid:{ik}:{ver}")

    for key in (
        "SIGNAL_SUPABASE_WRITES_ENABLED",
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
        "SIGNAL_CLOUD_SYNC_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED",
        "TESTNET_ORDER_SUBMISSION_APPROVED",
        "PERPETUAL_AUTO_EXECUTION_ENABLED",
    ):
        _gate_off(env_text, key)
    _gate_off(env_text, "AGENT_ALLOW_LIVE", allow_unset=False)
    # AGENT_ALLOW_LIVE must be explicitly false in env from earlier checks
    m = re.search(r"^AGENT_ALLOW_LIVE=(.*)$", env_text, re.M)
    if not m or m.group(1).strip().lower() not in {"false", "0", "no"}:
        _fail("AGENT_ALLOW_LIVE_not_false")

    raw = os.environ.get("DATABASE_URL") or ""
    if not raw.strip():
        _fail("DATABASE_URL_missing")
    info = inspect_database_url(raw)
    ref = extract_project_ref(host=info.host, user=info.user)
    if ref != EXPECTED_PROJECT:
        _fail(f"project_ref_mismatch:{ref}")
    if "ap-southeast-2" not in (info.host or ""):
        _fail("region_host_mismatch")

    # Process env for Alembic guards (session-only; do not rewrite .env)
    os.environ["CRYPTONOVA_DB_TARGET"] = "development"
    os.environ["CRYPTONOVA_DEV_PROJECT_REF"] = EXPECTED_PROJECT
    os.environ["CRYPTONOVA_USE_DATABASE_URL_AS_DEV"] = "true"
    os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "yes"

    identity = verify_dev_database_target(require_migration_approval=True, connect=False)
    if identity.project_ref != EXPECTED_PROJECT:
        _fail("identity_ref_mismatch")

    url = normalize_database_url(raw, require_ssl_for_remote=True)
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        if rev != EXPECTED_BEFORE:
            _fail(f"remote_revision_unexpected:{rev}")
        for table in EXPECTED_TABLES:
            exists = c.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='app' AND table_name=:t"
                ),
                {"t": table},
            ).scalar()
            if exists:
                _fail(f"target_table_already_exists:{table}")
        for table in EXISTING_TABLES:
            exists = c.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='app' AND table_name=:t"
                ),
                {"t": table},
            ).scalar()
            if not exists:
                _fail(f"existing_table_missing:{table}")
    print("precheck_ok")
    print("checksum_ok", digest)
    print("backup_ok", BACKUP.name)
    print("remote_revision_before", EXPECTED_BEFORE)
    print("project_ref", ref)
    print("host", info.host)
    return {"url": url, "digest": digest, "host": info.host, "ref": ref}


def promote() -> None:
    if ACTIVE.exists():
        active_digest = hashlib.sha256(ACTIVE.read_bytes()).hexdigest()
        proposed_digest = hashlib.sha256(PROPOSED.read_bytes()).hexdigest()
        if active_digest != proposed_digest:
            _fail("active_migration_differs_from_proposed")
        print("promote_already_present_matching")
        return
    shutil.copy2(PROPOSED, ACTIVE)
    if hashlib.sha256(ACTIVE.read_bytes()).hexdigest() != EXPECTED_SHA:
        _fail("promote_checksum_mismatch")
    print("promote_ok")


def run_upgrade() -> int:
    cmd = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        str(ROOT / "apps" / "api" / "alembic.ini"),
        "upgrade",
        EXPECTED_AFTER,
    ]
    print("alembic_cmd", "uv/python -m alembic -c apps/api/alembic.ini upgrade 20261107_0004")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    # Sanitize: never echo env; strip possible URL-looking fragments from stderr/stdout
    out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    safe_lines = []
    for line in out.splitlines():
        low = line.lower()
        if "password" in low or "postgresql://" in low or "postgres://" in low:
            safe_lines.append("[redacted_line]")
        else:
            safe_lines.append(line)
    print("alembic_exit", proc.returncode)
    print("alembic_output_sanitized_begin")
    print("\n".join(safe_lines[-80:]))
    print("alembic_output_sanitized_end")
    return proc.returncode


def verify(url: str) -> dict:
    engine = create_engine(url, pool_pre_ping=True)
    report: dict = {"tables": {}, "policies": {}, "existing": {}, "rls": {}}
    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        report["alembic_revision"] = rev
        for table in EXPECTED_TABLES:
            exists = c.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='app' AND table_name=:t"
                ),
                {"t": table},
            ).scalar()
            report["tables"][table] = bool(exists)
            if exists:
                rls = c.execute(
                    text(
                        "SELECT relrowsecurity FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='app' AND c.relname=:t"
                    ),
                    {"t": table},
                ).scalar()
                report["rls"][table] = bool(rls)
                pol = c.execute(
                    text(
                        "SELECT polname FROM pg_policy p "
                        "JOIN pg_class c ON c.oid=p.polrelid "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='app' AND c.relname=:t"
                    ),
                    {"t": table},
                ).fetchall()
                report["policies"][table] = [r[0] for r in pol]
                n = c.execute(text(f'SELECT COUNT(*) FROM app."{table}"')).scalar()
                report.setdefault("row_counts", {})[table] = int(n or 0)
        for table in EXISTING_TABLES:
            exists = c.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='app' AND table_name=:t"
                ),
                {"t": table},
            ).scalar()
            report["existing"][table] = bool(exists)
        # constraint / index samples
        uq = c.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid='app.signal_history'::regclass AND contype='u' "
                "ORDER BY conname"
            )
        ).fetchall()
        report["signal_history_uniques"] = [r[0] for r in uq]
        idxs = c.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname='app' AND tablename='signal_history' "
                "ORDER BY indexname"
            )
        ).fetchall()
        report["signal_history_indexes"] = [r[0] for r in idxs]
        fks = c.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid='app.signal_agent_contributions'::regclass "
                "AND contype='f'"
            )
        ).fetchall()
        report["contrib_fks"] = [r[0] for r in fks]
    return report


def disable_guard() -> None:
    os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "false"
    print("migration_guard_disabled_session=true")


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    print("gate_b_start", started)
    url = ""
    try:
        meta = prechecks()
        url = meta["url"]
        promote()
        code = run_upgrade()
        if code != 0:
            disable_guard()
            print("STATUS:MIGRATION_FAILED")
            return code
        report = verify(url)
        print("remote_revision_after", report.get("alembic_revision"))
        print("verify_tables", report.get("tables"))
        print("verify_rls", report.get("rls"))
        print("verify_policies", report.get("policies"))
        print("verify_existing", report.get("existing"))
        print("verify_row_counts", report.get("row_counts"))
        print("verify_uniques", report.get("signal_history_uniques"))
        print("verify_indexes", report.get("signal_history_indexes"))
        print("verify_fks", report.get("contrib_fks"))
        ok = (
            report.get("alembic_revision") == EXPECTED_AFTER
            and all(report.get("tables", {}).values())
            and all(report.get("existing", {}).values())
            and all(report.get("rls", {}).values())
            and all(
                f"{t}_select_own" in (report.get("policies") or {}).get(t, [])
                for t in EXPECTED_TABLES
            )
        )
        disable_guard()
        if ok:
            print("STATUS:MIGRATION_VERIFIED")
            return 0
        print("STATUS:MIGRATION_FAILED_VERIFICATION")
        return 3
    except SystemExit:
        disable_guard()
        raise
    except Exception as exc:  # noqa: BLE001
        disable_guard()
        print(f"FAIL:exception:{type(exc).__name__}")
        print("STATUS:MIGRATION_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
