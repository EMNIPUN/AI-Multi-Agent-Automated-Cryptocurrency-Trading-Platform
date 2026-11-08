"""
Gate 62 execute 20261108_0005 — Option A least-privilege roles/grants/RLS.

Requires explicit operator approval already obtained for project
wmirifmgaftassgrfbyl + revision + checksum.

Does NOT: Gate 63 credential cutover, cloud writes/sync/import, exchange orders.
Restores CRYPTONOVA_ALLOW_DEV_MIGRATIONS=false after attempt.
Never prints DATABASE_URL or passwords.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
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

EXPECTED_SHA = "9e0efdd317926a7ce5959f87e77c60c122e87ec62c49345597840cc6307f318a"
EXPECTED_PROJECT = "wmirifmgaftassgrfbyl"
EXPECTED_BEFORE = "20261107_0004"
EXPECTED_AFTER = "20261108_0005"
MIG_NAME = "20261108_0005_option_a_least_privilege.py"
PROPOSED = ROOT / "apps" / "api" / "alembic" / "versions_proposed" / MIG_NAME
ACTIVE = ROOT / "apps" / "api" / "alembic" / "versions" / MIG_NAME

RUNTIME_ROLE = "cryptonova_api_runtime"
MIGRATOR_ROLE = "cryptonova_migrator"

SIGNAL_WRITE = (
    "signal_history",
    "signal_agent_contributions",
    "signal_risk_events",
)
SCHEDULER_READ = (
    "scheduler_evaluation_history",
    "scheduler_audit",
)
CATALOG_READ = (
    "agent_decisions",
    "system_events",
    "strategy_configs",
    "exchange_account_bindings",
)
PHASE4D_COUNT_TABLES = SIGNAL_WRITE + SCHEDULER_READ


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

    for key in (
        "SIGNAL_SUPABASE_WRITES_ENABLED",
        "SIGNAL_SUPABASE_WRITES_OPERATOR_APPROVED",
        "SIGNAL_CLOUD_SYNC_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_ENABLED",
        "EXCHANGE_BINDING_PERSISTENCE_OPERATOR_APPROVED",
        "TESTNET_ORDER_SUBMISSION_APPROVED",
        "PERPETUAL_AUTO_EXECUTION_ENABLED",
        "RUNTIME_DB_IDENTITY_ENABLED",
    ):
        _gate_off(env_text, key)
    _gate_off(env_text, "AGENT_ALLOW_LIVE", allow_unset=False)
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
        role_count = c.execute(
            text("SELECT COUNT(*) FROM pg_roles WHERE rolname LIKE 'cryptonova_%'")
        ).scalar()
        if int(role_count or 0) != 0:
            _fail(f"cryptonova_roles_already_present:{role_count}")
        for table in PHASE4D_COUNT_TABLES:
            n = c.execute(text(f'SELECT COUNT(*) FROM app."{table}"')).scalar()
            if int(n or 0) != 0:
                _fail(f"unexpected_row_count:{table}:{n}")
        server = c.execute(text("SHOW server_version")).scalar()
        session_user = c.execute(text("SELECT session_user")).scalar()

    print("precheck_ok")
    print("checksum_ok", digest)
    print("remote_revision_before", EXPECTED_BEFORE)
    print("project_ref", ref)
    print("host", info.host)
    print("server_version", server)
    print("session_user", session_user)
    print("cryptonova_roles_before", 0)
    print("phase4d_counts_before", 0)
    print("backup_pitr", "NOT_VERIFIED_OPERATOR_ACCEPTED")
    return {"url": url, "digest": digest, "host": info.host, "ref": ref}


def promote() -> None:
    if ACTIVE.exists():
        active_digest = hashlib.sha256(ACTIVE.read_bytes()).hexdigest()
        proposed_digest = hashlib.sha256(PROPOSED.read_bytes()).hexdigest()
        if active_digest != proposed_digest:
            _fail("active_migration_differs_from_proposed")
        if active_digest != EXPECTED_SHA:
            _fail("active_checksum_mismatch")
        print("promote_already_present_matching")
        return
    shutil.copy2(PROPOSED, ACTIVE)
    if hashlib.sha256(ACTIVE.read_bytes()).hexdigest() != EXPECTED_SHA:
        _fail("promote_checksum_mismatch")
    print("promote_ok")
    print("active_sha256", EXPECTED_SHA)


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
    print("alembic_cmd", "python -m alembic -c apps/api/alembic.ini upgrade 20261108_0005")
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
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
    report: dict = {
        "roles": {},
        "runtime_policies": {},
        "authenticated_policies": {},
        "row_counts": {},
        "grants_sample": {},
    }
    with engine.connect() as c:
        rev = c.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        report["alembic_revision"] = rev
        for role in (RUNTIME_ROLE, MIGRATOR_ROLE):
            row = c.execute(
                text(
                    """
                    SELECT rolname, rolcanlogin, rolbypassrls, rolsuper, rolinherit
                    FROM pg_roles WHERE rolname = :r
                    """
                ),
                {"r": role},
            ).fetchone()
            if row is None:
                report["roles"][role] = None
            else:
                report["roles"][role] = {
                    "login": bool(row[1]),
                    "bypassrls": bool(row[2]),
                    "super": bool(row[3]),
                    "inherit": bool(row[4]),
                }
        for table in SIGNAL_WRITE + SCHEDULER_READ + CATALOG_READ:
            pols = c.execute(
                text(
                    """
                    SELECT policyname FROM pg_policies
                    WHERE schemaname='app' AND tablename=:t
                    ORDER BY policyname
                    """
                ),
                {"t": table},
            ).fetchall()
            names = [r[0] for r in pols]
            report["runtime_policies"][table] = [
                n for n in names if "_runtime_" in n
            ]
            report["authenticated_policies"][table] = [
                n for n in names if n.endswith("_select_own") and "_runtime_" not in n
            ]
        for table in PHASE4D_COUNT_TABLES:
            n = c.execute(text(f'SELECT COUNT(*) FROM app."{table}"')).scalar()
            report["row_counts"][table] = int(n or 0)
        # Sample grants for runtime on signal_history
        grants = c.execute(
            text(
                """
                SELECT privilege_type
                FROM information_schema.role_table_grants
                WHERE table_schema='app' AND table_name='signal_history'
                  AND grantee=:g
                ORDER BY privilege_type
                """
            ),
            {"g": RUNTIME_ROLE},
        ).fetchall()
        report["grants_sample"]["signal_history_runtime"] = [r[0] for r in grants]
        mig_create = c.execute(
            text(
                """
                SELECT has_schema_privilege(:r, 'app', 'CREATE')
                """
            ),
            {"r": MIGRATOR_ROLE},
        ).scalar()
        report["migrator_create_on_app"] = bool(mig_create)
    return report


def disable_guard() -> None:
    os.environ["CRYPTONOVA_ALLOW_DEV_MIGRATIONS"] = "false"
    print("migration_guard_disabled_session=true")


def main() -> int:
    started = datetime.now(timezone.utc).isoformat()
    print("gate_62_start", started)
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
        print("verify_roles", report.get("roles"))
        print("verify_runtime_policies", report.get("runtime_policies"))
        print("verify_authenticated_policies", report.get("authenticated_policies"))
        print("verify_row_counts", report.get("row_counts"))
        print("verify_grants_sample", report.get("grants_sample"))
        print("verify_migrator_create_on_app", report.get("migrator_create_on_app"))

        roles = report.get("roles") or {}
        runtime = roles.get(RUNTIME_ROLE) or {}
        migrator = roles.get(MIGRATOR_ROLE) or {}
        counts_ok = all(v == 0 for v in (report.get("row_counts") or {}).values())
        runtime_pols_ok = all(
            f"{t}_runtime_select_own" in (report.get("runtime_policies") or {}).get(t, [])
            for t in SIGNAL_WRITE + SCHEDULER_READ + CATALOG_READ
        )
        write_pols_ok = all(
            f"{t}_runtime_insert_own" in (report.get("runtime_policies") or {}).get(t, [])
            and f"{t}_runtime_update_own"
            in (report.get("runtime_policies") or {}).get(t, [])
            for t in SIGNAL_WRITE
        )
        auth_pols_ok = all(
            f"{t}_select_own"
            in (report.get("authenticated_policies") or {}).get(t, [])
            for t in SIGNAL_WRITE + SCHEDULER_READ + CATALOG_READ
        )
        role_attrs_ok = (
            runtime
            and migrator
            and runtime.get("login") is False
            and runtime.get("bypassrls") is False
            and runtime.get("super") is False
            and runtime.get("inherit") is True
            and migrator.get("login") is False
            and migrator.get("bypassrls") is False
            and migrator.get("super") is False
            and migrator.get("inherit") is True
        )
        grants_ok = set(report.get("grants_sample", {}).get("signal_history_runtime", [])) >= {
            "SELECT",
            "INSERT",
            "UPDATE",
        }
        ok = (
            report.get("alembic_revision") == EXPECTED_AFTER
            and role_attrs_ok
            and counts_ok
            and runtime_pols_ok
            and write_pols_ok
            and auth_pols_ok
            and grants_ok
            and report.get("migrator_create_on_app") is True
        )
        disable_guard()
        if ok:
            print("STATUS:MIGRATION_VERIFIED")
            print("gate_63_not_performed=true")
            print("cloud_writes_not_enabled=true")
            print("orders_not_enabled=true")
            return 0
        print("STATUS:MIGRATION_FAILED_VERIFICATION")
        return 3
    except SystemExit:
        disable_guard()
        raise
    except Exception:  # noqa: BLE001
        disable_guard()
        print(f"FAIL:exception:{sys.exc_info()[0].__name__ if sys.exc_info()[0] else 'Error'}")
        print("STATUS:MIGRATION_FAILED")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
