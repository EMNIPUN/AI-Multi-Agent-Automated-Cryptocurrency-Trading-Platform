"""Environment identity guard tests — synthetic fixtures only."""

from __future__ import annotations

import pytest

from scripts.verify_dev_database_target import (
    DEFAULT_APPROVED_DEV_PROJECT_REFS,
    DevTargetError,
    extract_project_ref,
    verify_dev_database_target,
)

APPROVED_DEV = next(iter(DEFAULT_APPROVED_DEV_PROJECT_REFS))
OTHER_REF = "abcdefghijklmnop"
FUTURE_PROD = "zzprodref999999"


def _base(**extra: str) -> dict[str, str]:
    env = {
        "CRYPTONOVA_DB_TARGET": "development",
        "CRYPTONOVA_DEV_PROJECT_REF": APPROVED_DEV,
        "DEV_DATABASE_URL": (
            f"postgresql://postgres.{APPROVED_DEV}:secret@"
            f"aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
        ),
    }
    env.update(extra)
    return env


def test_extract_project_ref_direct_and_pooler() -> None:
    assert (
        extract_project_ref(host=f"db.{APPROVED_DEV}.supabase.co", user="postgres")
        == APPROVED_DEV
    )
    assert (
        extract_project_ref(
            host="aws-0-ap-southeast-2.pooler.supabase.com",
            user=f"postgres.{APPROVED_DEV}",
        )
        == APPROVED_DEV
    )


def test_rejects_missing_target() -> None:
    with pytest.raises(DevTargetError, match="missing_db_target"):
        verify_dev_database_target({})


def test_rejects_production_classification() -> None:
    with pytest.raises(DevTargetError, match="production_target_forbidden"):
        verify_dev_database_target(_base(**{"CRYPTONOVA_DB_TARGET": "production"}))


def test_rejects_ambiguous_classification() -> None:
    with pytest.raises(DevTargetError, match="ambiguous_db_target"):
        verify_dev_database_target(_base(**{"CRYPTONOVA_DB_TARGET": "staging"}))


def test_rejects_missing_dev_project_ref() -> None:
    env = _base()
    del env["CRYPTONOVA_DEV_PROJECT_REF"]
    with pytest.raises(DevTargetError, match="missing_dev_project_ref"):
        verify_dev_database_target(env)


def test_rejects_unknown_dev_project_not_in_allowlist() -> None:
    env = _base(
        CRYPTONOVA_DEV_PROJECT_REF=OTHER_REF,
        DEV_DATABASE_URL=(
            f"postgresql://postgres.{OTHER_REF}:secret@"
            f"aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
        ),
    )
    with pytest.raises(DevTargetError, match="dev_project_ref_not_in_allowlist"):
        verify_dev_database_target(env)


def test_rejects_future_production_deny_list() -> None:
    env = _base(
        CRYPTONOVA_DEV_PROJECT_REF=FUTURE_PROD,
        CRYPTONOVA_APPROVED_DEV_PROJECT_REFS=FUTURE_PROD,
        CRYPTONOVA_PROD_PROJECT_REFS=FUTURE_PROD,
        DEV_DATABASE_URL=(
            f"postgresql://postgres.{FUTURE_PROD}:secret@"
            f"aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
        ),
    )
    with pytest.raises(DevTargetError, match="dev_project_ref_matches_production"):
        verify_dev_database_target(env)


def test_rejects_hostname_project_ref_mismatch() -> None:
    env = _base(
        DEV_DATABASE_URL=(
            f"postgresql://postgres.{OTHER_REF}:secret@"
            f"aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
        )
    )
    with pytest.raises(DevTargetError, match="project_ref_hostname_mismatch"):
        verify_dev_database_target(env)


def test_rejects_missing_database_url() -> None:
    env = _base()
    del env["DEV_DATABASE_URL"]
    with pytest.raises(DevTargetError, match="missing_dev_database_url"):
        verify_dev_database_target(env)


def test_accepts_database_url_with_explicit_dev_opt_in() -> None:
    env = {
        "CRYPTONOVA_DB_TARGET": "development",
        "CRYPTONOVA_DEV_PROJECT_REF": APPROVED_DEV,
        "CRYPTONOVA_USE_DATABASE_URL_AS_DEV": "true",
        "DATABASE_URL": (
            f"postgresql://postgres.{APPROVED_DEV}:secret@"
            f"aws-0-ap-southeast-2.pooler.supabase.com:5432/postgres?sslmode=require"
        ),
    }
    identity = verify_dev_database_target(env)
    assert identity.project_ref == APPROVED_DEV


def test_accepts_matching_approved_dev_pooler_url() -> None:
    identity = verify_dev_database_target(_base())
    assert identity.classification == "development"
    assert identity.project_ref == APPROVED_DEV
    assert identity.host == "aws-0-ap-southeast-2.pooler.supabase.com"
    assert "***" in identity.redacted_url
    assert identity.migrations_approved is False


def test_migration_approval_required() -> None:
    with pytest.raises(DevTargetError, match="migrations_not_approved"):
        verify_dev_database_target(_base(), require_migration_approval=True)
    identity = verify_dev_database_target(
        _base(CRYPTONOVA_ALLOW_DEV_MIGRATIONS="yes"),
        require_migration_approval=True,
    )
    assert identity.migrations_approved is True


def test_local_disposable_requires_flag() -> None:
    env = _base(
        DEV_DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:5432/cryptonova_dev"
    )
    with pytest.raises(DevTargetError, match="local_db_requires"):
        verify_dev_database_target(env)
    identity = verify_dev_database_target(
        {**env, "CRYPTONOVA_ALLOW_LOCAL_DISPOSABLE_DB": "true"}
    )
    assert identity.host == "127.0.0.1"
