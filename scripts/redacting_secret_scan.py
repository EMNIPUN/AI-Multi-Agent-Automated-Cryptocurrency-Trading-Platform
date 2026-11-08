"""Redacting secret scan — path + category + count only. Never print match text."""
from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = {
    "pem_private_key_block": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    "jwt_like_triple": re.compile(
        r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
    ),
    "postgres_url_with_password": re.compile(
        r"postgres(?:ql)?://[^:\s/]+:[^@\s/]+@", re.I
    ),
    "bybit_secret_assignment": re.compile(
        r"(?i)(BYBIT_[A-Z0-9_]*API_SECRET|API_SECRET)\s*=\s*['\"][A-Za-z0-9+/_-]{16,}['\"]"
    ),
    "aws_access_key_id": re.compile(r"AKIA[0-9A-Z]{16}"),
}

SOFT = {
    "env_var_name_only": re.compile(
        r"(?i)\b(BYBIT_API_KEY|BYBIT_API_SECRET|DATABASE_URL|"
        r"SUPABASE_SERVICE_ROLE|SUPABASE_JWT_SECRET|SERVICE_ROLE)\b"
    ),
    "placeholder_value": re.compile(
        r"(?i)(your_api_key_here|changeme|placeholder|test-only-hs256|example\.supabase)"
    ),
}

SKIP_DIR = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "htmlcov",
}
SKIP_SUFFIX = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".lock",
    ".pyc",
}


def _git_z(args: list[str]) -> list[Path]:
    out = subprocess.check_output(["git", *args, "-z"], cwd=ROOT, text=True, errors="replace")
    return [Path(p) for p in out.split("\0") if p]


def main() -> None:
    findings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    soft_findings: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    scanned = 0
    errors = 0
    seen: set[str] = set()
    env_local = (ROOT / "apps" / "web" / ".env.local").is_file()

    for rel in _git_z(["ls-files"]) + _git_z(["ls-files", "--others", "--exclude-standard"]):
        key = rel.as_posix()
        if key in seen:
            continue
        seen.add(key)
        if any(part in SKIP_DIR for part in rel.parts):
            continue
        if rel.suffix.lower() in SKIP_SUFFIX:
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            errors += 1
            continue
        scanned += 1
        for cat, rx in PATTERNS.items():
            n = len(rx.findall(text))
            if not n:
                continue
            if cat == "jwt_like_triple" and (
                "test-only" in text
                or "example.supabase" in text
                or key.startswith("tests/")
                or "StaticMappingVerifier" in text
            ):
                soft_findings["jwt_like_in_tests_or_docs"][key] += n
                continue
            findings[cat][key] += n
        for cat, rx in SOFT.items():
            n = len(rx.findall(text))
            if n:
                soft_findings[cat][key] += n

    print("SCANNED_FILES", scanned)
    print("READ_ERRORS", errors)
    print("IGNORED_ENV_LOCAL_EXISTS", env_local)
    print("HIGH_CONFIDENCE_CATEGORIES", len(findings))
    for cat, paths in sorted(findings.items()):
        print(f"HIGH|{cat}|files={len(paths)}|hits={sum(paths.values())}")
        for p in sorted(paths)[:30]:
            print(f"  PATH|{cat}|{p}|count={paths[p]}")
    print("SOFT_CATEGORIES", len(soft_findings))
    for cat, paths in sorted(soft_findings.items()):
        print(f"SOFT|{cat}|files={len(paths)}|hits={sum(paths.values())}")


if __name__ == "__main__":
    main()
