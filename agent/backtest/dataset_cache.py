"""
Local content-addressed historical dataset cache (Prompt 68C).

Stores under ``data/backtests/datasets/`` — never under operator paper journals.
Never exposes arbitrary filesystem paths through the web API.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.backtest.artifacts import atomic_write_text, default_results_dir
from agent.backtest.data import candle_content_hash, candles_to_rows, rows_to_candles
from agent.backtest.limits import DEFAULT_MAX_CACHED_DATASET_BYTES, DEFAULT_MAX_CACHE_TOTAL_BYTES
from agent.market_data import Candle

HASH_RE = re.compile(r"^[a-f0-9]{64}$")
DATASETS_DIRNAME = "datasets"


class DatasetCacheError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CachedDataset:
    content_hash: str
    candles: tuple[Candle, ...]
    meta: dict[str, Any]
    path: Path


def default_datasets_dir(repo_root: str | Path | None = None) -> Path:
    return default_results_dir(repo_root) / DATASETS_DIRNAME


def _validate_hash(content_hash: str) -> str:
    h = (content_hash or "").strip().lower()
    if not HASH_RE.fullmatch(h):
        raise DatasetCacheError("invalid_hash", "dataset hash must be 64 hex chars")
    return h


def dataset_path_for_hash(datasets_dir: Path, content_hash: str) -> Path:
    h = _validate_hash(content_hash)
    root = Path(datasets_dir).resolve()
    candidate = (root / f"{h}.json").resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DatasetCacheError("path_escape", "dataset path escapes cache root") from exc
    return candidate


def _dir_size_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for p in root.rglob("*.json"):
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


def save_dataset_cache(
    candles: list[Candle] | tuple[Candle, ...],
    *,
    meta: dict[str, Any],
    datasets_dir: str | Path | None = None,
    max_file_bytes: int = DEFAULT_MAX_CACHED_DATASET_BYTES,
    max_total_bytes: int = DEFAULT_MAX_CACHE_TOTAL_BYTES,
) -> CachedDataset:
    """Atomically write a content-addressed dataset JSON file."""
    series = tuple(candles)
    if not series:
        raise DatasetCacheError("empty_dataset", "cannot cache empty candle series")
    content_hash = candle_content_hash(series)
    root = Path(datasets_dir) if datasets_dir is not None else default_datasets_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = dataset_path_for_hash(root, content_hash)

    body = {
        "meta": {
            **meta,
            "content_hash": content_hash,
            "candle_count": len(series),
            "cached_ms": int(time.time() * 1000),
            "label": str(meta.get("label") or meta.get("provenance") or "CACHED HISTORICAL DATASET"),
        },
        "candles": candles_to_rows(series),
    }
    text = json.dumps(body, indent=2, sort_keys=True)
    size = len(text.encode("utf-8"))
    if size > max_file_bytes:
        raise DatasetCacheError(
            "dataset_too_large",
            f"dataset JSON {size} bytes exceeds max {max_file_bytes}",
        )
    # Allow overwrite of identical hash; only check budget when creating new file.
    if not path.exists():
        current = _dir_size_bytes(root)
        if current + size > max_total_bytes:
            raise DatasetCacheError(
                "cache_budget_exceeded",
                f"cache would exceed {max_total_bytes} bytes",
            )
    atomic_write_text(path, text)
    return CachedDataset(
        content_hash=content_hash,
        candles=series,
        meta=dict(body["meta"]),
        path=path,
    )


def load_dataset_cache(
    content_hash: str,
    *,
    datasets_dir: str | Path | None = None,
    expected: dict[str, Any] | None = None,
    max_file_bytes: int = DEFAULT_MAX_CACHED_DATASET_BYTES,
) -> CachedDataset:
    """
    Load and integrity-check a cached dataset.

    Always recomputes content hash and rejects mismatches / corrupt files.
    Optional ``expected`` keys (symbol, interval, market_type) must match meta.
    """
    root = Path(datasets_dir) if datasets_dir is not None else default_datasets_dir()
    path = dataset_path_for_hash(root, content_hash)
    if not path.exists():
        raise DatasetCacheError("cache_miss", f"no cached dataset for {content_hash[:12]}…")
    if path.is_symlink():
        raise DatasetCacheError("symlink_rejected", "cached dataset must not be a symlink")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise DatasetCacheError("cache_unreadable", "unable to stat cache file") from exc
    if size <= 0:
        raise DatasetCacheError("empty_cache", "cache file is empty")
    if size > max_file_bytes:
        raise DatasetCacheError("dataset_too_large", "cache file exceeds size cap")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatasetCacheError("corrupt_cache", "cache JSON unreadable") from exc
    if not isinstance(payload, dict):
        raise DatasetCacheError("corrupt_cache", "cache root must be object")
    meta = dict(payload.get("meta") or {})
    rows = payload.get("candles") or payload.get("ohlcv") or []
    if not isinstance(rows, list):
        raise DatasetCacheError("corrupt_cache", "candles must be a list")
    candles = tuple(rows_to_candles(rows))
    recomputed = candle_content_hash(candles)
    stored = str(meta.get("content_hash") or "").lower()
    requested = _validate_hash(content_hash)
    if recomputed != requested:
        raise DatasetCacheError(
            "hash_mismatch",
            "recomputed candle hash does not match requested identity",
        )
    if stored and stored != recomputed:
        raise DatasetCacheError(
            "hash_mismatch",
            "stored meta content_hash does not match candle body",
        )
    if expected:
        if expected.get("symbol") is not None:
            if str(meta.get("symbol") or "").upper() != str(expected["symbol"]).upper():
                raise DatasetCacheError("identity_mismatch", "cached symbol mismatch")
        if expected.get("interval") is not None:
            if str(meta.get("interval") or "") != str(expected["interval"]):
                raise DatasetCacheError("identity_mismatch", "cached interval mismatch")
        if expected.get("market_type") is not None:
            if str(meta.get("market_type") or "").lower() != str(expected["market_type"]).lower():
                raise DatasetCacheError("identity_mismatch", "cached market_type mismatch")
    return CachedDataset(
        content_hash=recomputed,
        candles=candles,
        meta=meta,
        path=path,
    )


def resolve_cache_key_path_only(content_hash: str, datasets_dir: Path) -> Path:
    """Safe path resolver for operators — never accepts absolute user paths."""
    return dataset_path_for_hash(datasets_dir, content_hash)
