"""
Discoverable, read-safe persistence for 68A backtest JSON reports.

Does not mutate result_hash. Isolated under data/backtests/ by default.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from agent.backtest.models import BacktestResult
from agent.backtest.report import write_json_report

# Canonical local results root (relative to repo when not overridden).
DEFAULT_RESULTS_DIRNAME = "data/backtests"
RUN_ID_RE = re.compile(r"^bt_[A-Za-z0-9]{8,32}$")
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024  # 8 MiB hard cap for readers


class ArtifactError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def default_results_dir(repo_root: str | Path | None = None) -> Path:
    if repo_root is None:
        # agent/backtest/artifacts.py → repo root is parents[2]
        repo_root = Path(__file__).resolve().parents[2]
    return Path(repo_root) / "data" / "backtests"


def validate_run_id(run_id: str) -> str:
    rid = (run_id or "").strip()
    if not RUN_ID_RE.fullmatch(rid):
        raise ArtifactError("invalid_run_id", "run_id must match bt_[A-Za-z0-9]{8,32}")
    return rid


def report_filename(run_id: str) -> str:
    return f"{validate_run_id(run_id)}_report.json"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def persist_run_artifact(
    result: BacktestResult,
    *,
    results_dir: str | Path | None = None,
) -> Path:
    """
    Atomically write ``{run_id}_report.json`` under the results directory.

    Does not alter ``result_hash``. Safe for concurrent readers via replace.
    """
    root = Path(results_dir) if results_dir is not None else default_results_dir()
    root.mkdir(parents=True, exist_ok=True)
    out = root / report_filename(result.run_id)
    payload = json.dumps(result.to_public_dict(), indent=2, sort_keys=True)
    atomic_write_text(out, payload)
    return out


def resolve_results_root(results_dir: str | Path) -> Path:
    root = Path(results_dir).resolve()
    if not root.exists():
        return root
    if not root.is_dir():
        raise ArtifactError("results_not_directory", "results path is not a directory")
    return root


def _safe_resolve_under(root: Path, candidate: Path) -> Path:
    """Resolve candidate and ensure it stays under root (no symlink escape)."""
    root_res = root.resolve()
    # Resolve without following final symlink for existence check first.
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise ArtifactError("path_resolve_failed", "unable to resolve artifact path") from exc
    try:
        resolved.relative_to(root_res)
    except ValueError as exc:
        raise ArtifactError("path_escape", "artifact path escapes results directory") from exc
    if candidate.is_symlink() or resolved.is_symlink():
        # After resolve, ensure target still under root.
        target = resolved.resolve(strict=False)
        try:
            target.relative_to(root_res)
        except ValueError as exc:
            raise ArtifactError("symlink_escape", "symlink escapes results directory") from exc
        return target
    return resolved


def list_report_paths(results_dir: str | Path) -> list[Path]:
    root = resolve_results_root(results_dir)
    if not root.exists():
        return []
    out: list[Path] = []
    for path in sorted(root.glob("bt_*_report.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        try:
            safe = _safe_resolve_under(root, path)
        except ArtifactError:
            continue
        name = safe.name
        if not name.endswith("_report.json"):
            continue
        rid = name[: -len("_report.json")]
        try:
            validate_run_id(rid)
        except ArtifactError:
            continue
        out.append(safe)
    return out


def load_run_payload(
    results_dir: str | Path,
    run_id: str,
    *,
    max_bytes: int = MAX_ARTIFACT_BYTES,
) -> dict[str, Any]:
    rid = validate_run_id(run_id)
    root = resolve_results_root(results_dir)
    if not root.exists():
        raise ArtifactError("results_missing", "backtest results directory not found")
    candidate = root / report_filename(rid)
    if not candidate.exists():
        raise ArtifactError("run_not_found", f"no report for {rid}")
    path = _safe_resolve_under(root, candidate)
    if not path.is_file():
        raise ArtifactError("run_not_found", f"no report for {rid}")
    size = path.stat().st_size
    if size <= 0:
        raise ArtifactError("empty_artifact", "report file is empty")
    if size > max_bytes:
        raise ArtifactError("artifact_too_large", f"report exceeds {max_bytes} bytes")
    try:
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ArtifactError("corrupt_json", "report JSON is corrupt") from exc
    except OSError as exc:
        raise ArtifactError("read_failed", "unable to read report") from exc
    if not isinstance(data, dict):
        raise ArtifactError("invalid_artifact", "report root must be an object")
    # Soft identity check — do not invent fields.
    reported = data.get("run_id")
    if reported is not None and str(reported) != rid:
        raise ArtifactError("run_id_mismatch", "artifact run_id does not match path")
    return data


# Keep write_json_report import used for compatibility re-export in demos.
__all__ = [
    "ArtifactError",
    "DEFAULT_RESULTS_DIRNAME",
    "MAX_ARTIFACT_BYTES",
    "RUN_ID_RE",
    "atomic_write_text",
    "default_results_dir",
    "list_report_paths",
    "load_run_payload",
    "persist_run_artifact",
    "report_filename",
    "validate_run_id",
    "write_json_report",
]
