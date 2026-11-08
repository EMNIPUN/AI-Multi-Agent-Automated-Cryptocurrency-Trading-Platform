"""
Read-only RLS / privilege security inspection for the approved development DB.

Never prints passwords, connection strings, or JWT material.
Requires identity guard: CRYPTONOVA_DB_TARGET=development + approved project ref.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlalchemy import create_engine, text

from apps.api.app.database_url import normalize_database_url
from scripts.verify_dev_database_target import (
    DevTargetError,
    extract_project_ref,
    resolve_dev_database_url,
    summarize_identity,
    verify_dev_database_target,
)

EXPECTED_TABLES = (
    "agent_decisions",
    "system_events",
    "strategy_configs",
    "exchange_account_bindings",
)

EXPECTED_POLICIES = {
    "agent_decisions": "agent_decisions_select_own",
    "system_events": "system_events_select_own",
    "strategy_configs": "strategy_configs_select_own",
    "exchange_account_bindings": "exchange_account_bindings_select_own",
}


def main() -> int:
    try:
        identity = verify_dev_database_target(require_migration_approval=False, connect=False)
    except DevTargetError as exc:
        print(f"IDENTITY_REJECTED detail={exc}")
        return 2

    raw = resolve_dev_database_url(os.environ)
    url = normalize_database_url(raw, require_ssl_for_remote=True)
    eng = create_engine(url, pool_pre_ping=True)
    report: dict[str, object] = {
        "identity": summarize_identity(identity),
        "findings": [],
    }
    findings: list[str] = []

    with eng.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))

        ver = conn.execute(text("SELECT version_num FROM app.alembic_version")).scalar()
        report["alembic_version"] = ver
        if ver != "20261105_0003":
            findings.append(f"unexpected_alembic_version:{ver}")

        who = conn.execute(
            text(
                """
                SELECT current_user,
                       session_user,
                       current_database(),
                       inet_server_addr()::text
                """
            )
        ).one()
        report["session"] = {
            "current_user": who[0],
            "session_user": who[1],
            "database": who[2],
            # inet may be null via pooler — omit if empty
            "server_addr_present": bool(who[3]),
        }

        # Role privilege facts (no secrets)
        role_row = conn.execute(
            text(
                """
                SELECT r.rolname,
                       r.rolsuper,
                       r.rolbypassrls,
                       r.rolcanlogin
                FROM pg_roles r
                WHERE r.rolname = current_user
                """
            )
        ).one()
        report["current_role_privs"] = {
            "rolname": role_row[0],
            "rolsuper": bool(role_row[1]),
            "rolbypassrls": bool(role_row[2]),
            "rolcanlogin": bool(role_row[3]),
        }
        if role_row[1] or role_row[2]:
            findings.append(
                "app_connection_bypasses_rls:current_role_is_super_or_bypassrls"
            )

        # Table owner / RLS / force
        table_meta = []
        for t in EXPECTED_TABLES:
            row = conn.execute(
                text(
                    """
                    SELECT c.relname,
                           c.relrowsecurity,
                           c.relforcerowsecurity,
                           pg_get_userbyid(c.relowner) AS owner
                    FROM pg_class c
                    JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'app' AND c.relname = :t AND c.relkind = 'r'
                    """
                ),
                {"t": t},
            ).one_or_none()
            if row is None:
                findings.append(f"missing_table:{t}")
                table_meta.append({"table": t, "present": False})
                continue
            meta = {
                "table": row[0],
                "present": True,
                "rls_enabled": bool(row[1]),
                "rls_forced": bool(row[2]),
                "owner": row[3],
            }
            if not row[1]:
                findings.append(f"rls_disabled:{t}")
            if row[2]:
                findings.append(f"rls_forced:{t}")
            table_meta.append(meta)
        report["tables"] = table_meta

        # Policies
        policies = list(
            conn.execute(
                text(
                    """
                    SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
                    FROM pg_policies
                    WHERE schemaname = 'app'
                    ORDER BY 1, 2
                    """
                )
            )
        )
        policy_rows = []
        for tablename, policyname, permissive, roles, cmd, qual, with_check in policies:
            policy_rows.append(
                {
                    "table": tablename,
                    "policy": policyname,
                    "permissive": permissive,
                    "roles": roles,
                    "cmd": cmd,
                    "using": qual,
                    "with_check": with_check,
                }
            )
            expected = EXPECTED_POLICIES.get(tablename)
            if expected and policyname == expected:
                if cmd.upper() != "SELECT":
                    findings.append(f"policy_cmd_not_select:{policyname}")
                roles_l = [str(r).lower() for r in (roles or [])]
                if "authenticated" not in roles_l and "public" not in roles_l:
                    # pg_policies roles is array-ish; normalize
                    joined = ",".join(roles_l)
                    if "authenticated" not in joined:
                        findings.append(f"policy_role_unexpected:{policyname}:{joined}")
                using = (qual or "").lower()
                if "auth.uid()" not in using:
                    findings.append(f"policy_missing_auth_uid:{policyname}")
                if "current_setting" in using or "request.jwt" in using:
                    findings.append(f"policy_uses_untrusted_guc:{policyname}")
                if tablename == "exchange_account_bindings":
                    if "status" not in using or "active" not in using:
                        findings.append(
                            f"bindings_policy_missing_active_status:{policyname}"
                        )
                else:
                    if "owner_user_id is not null" not in using.replace("\n", " "):
                        # still ok if equality alone; catalog policies require NOT NULL
                        if "is not null" not in using:
                            findings.append(
                                f"catalog_policy_allows_null_owner:{policyname}"
                            )
        report["policies"] = policy_rows
        expected_names = set(EXPECTED_POLICIES.values())
        actual_names = {p["policy"] for p in policy_rows}
        missing_pols = sorted(expected_names - actual_names)
        extra_pols = sorted(actual_names - expected_names)
        if missing_pols:
            findings.append(f"missing_policies:{','.join(missing_pols)}")
        if extra_pols:
            findings.append(f"extra_policies:{','.join(extra_pols)}")

        # Grants on app schema / tables (non-secret)
        schema_grants = list(
            conn.execute(
                text(
                    """
                    SELECT grantee, privilege_type
                    FROM information_schema.usage_privileges
                    WHERE object_schema = 'app' OR object_name = 'app'
                    ORDER BY 1, 2
                    """
                )
            )
        )
        # Fallback: has_schema_privilege for key roles
        role_checks = {}
        for role in ("anon", "authenticated", "service_role", "authenticator", "postgres"):
            exists = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :r)"),
                {"r": role},
            ).scalar()
            if not exists:
                role_checks[role] = {"exists": False}
                continue
            usage = conn.execute(
                text("SELECT has_schema_privilege(:r, 'app', 'USAGE')"),
                {"r": role},
            ).scalar()
            create_priv = conn.execute(
                text("SELECT has_schema_privilege(:r, 'app', 'CREATE')"),
                {"r": role},
            ).scalar()
            table_select = {}
            for t in EXPECTED_TABLES:
                table_select[t] = bool(
                    conn.execute(
                        text(
                            "SELECT has_table_privilege(:r, 'app.' || :t, 'SELECT')"
                        ),
                        {"r": role, "t": t},
                    ).scalar()
                )
            bypass = conn.execute(
                text("SELECT rolbypassrls OR rolsuper FROM pg_roles WHERE rolname = :r"),
                {"r": role},
            ).scalar()
            role_checks[role] = {
                "exists": True,
                "schema_usage": bool(usage),
                "schema_create": bool(create_priv),
                "table_select": table_select,
                "bypass_or_super": bool(bypass),
            }
            if role in {"anon", "authenticated"} and usage:
                findings.append(f"schema_usage_granted:{role}")
            if role == "anon" and any(table_select.values()):
                findings.append("anon_has_table_select")
        report["role_privilege_matrix"] = role_checks
        report["schema_usage_privileges_rows"] = [
            {"grantee": g, "privilege": p} for g, p in schema_grants
        ]

        # auth.uid() function presence
        auth_uid = conn.execute(
            text(
                """
                SELECT EXISTS (
                  SELECT 1 FROM pg_proc p
                  JOIN pg_namespace n ON n.oid = p.pronamespace
                  WHERE n.nspname = 'auth' AND p.proname = 'uid'
                )
                """
            )
        ).scalar()
        report["auth_uid_function_exists"] = bool(auth_uid)
        if not auth_uid:
            findings.append("auth_uid_function_missing")

        # Row counts (empty expected)
        counts = {}
        for t in EXPECTED_TABLES:
            counts[t] = int(
                conn.execute(text(f"SELECT COUNT(*) FROM app.{t}")).scalar() or 0
            )
        report["row_counts"] = counts

        # Confirm project ref from connection user/host where possible
        from apps.api.app.database_url import inspect_database_url

        info = inspect_database_url(raw, require_ssl_for_remote=True)
        report["connection_project_ref"] = extract_project_ref(
            host=info.host, user=info.user
        )
        if report["connection_project_ref"] != identity.project_ref:
            findings.append("project_ref_mismatch_live_vs_guard")

    eng.dispose()
    report["findings"] = findings
    report["status"] = "PASS" if not findings else "FINDINGS"
    print("RLS_SECURITY_INSPECT_OK" if not findings else "RLS_SECURITY_INSPECT_FINDINGS")
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
