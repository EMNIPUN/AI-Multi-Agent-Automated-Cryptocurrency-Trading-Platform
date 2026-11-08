"""
Controlled backtest job queue + worker (Prompt 68C).

Lifecycle: QUEUED → RUNNING → COMPLETED | FAILED | INTERRUPTED
GET never starts execution. No live exchange orders. Isolated journals only.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from agent.backtest.artifacts import atomic_write_text, persist_run_artifact
from agent.backtest.config import BacktestConfig, DataSourceKind, RiskMode
from agent.backtest.dataset_cache import DatasetCacheError, load_dataset_cache
from agent.backtest.history_provider import (
    HistoryProviderError,
    HttpxHistoryTransport,
    estimate_candle_count,
    fetch_historical_candles,
    validate_history_request,
)
from agent.backtest.limits import (
    DEFAULT_MAX_CANDLES_PER_RUN,
    DEFAULT_MAX_QUEUED_RUNS,
    DEFAULT_MAX_RANGE_MS,
    DEFAULT_MAX_RUNTIME_SECONDS,
    DEFAULT_MAX_SIMULTANEOUS_RUNS,
    RUN_UI_DATA_SOURCES,
    RUN_UI_INTERVALS,
    RUN_UI_MARKET_TYPES,
    RUN_UI_RISK_MODES,
    RUN_UI_SYMBOLS,
)
from agent.backtest.models import BacktestStatus
from agent.backtest.runner import run_backtest
from apps.api.app.backtests.run_schemas import BacktestRunRequest

JOB_ID_PREFIX = "btj_"
LINEAR_LIMITATION = (
    "Linear historical candles still use spot-like long-only simulation — "
    "not a leveraged Futures backtest."
)


class RunServiceError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass
class JobRecord:
    job_id: str
    status: str
    created_ms: int
    request: dict[str, Any]
    idempotency_key: str | None = None
    started_ms: int | None = None
    finished_ms: int | None = None
    phase: str | None = None
    run_id: str | None = None
    dataset_hash: str | None = None
    result_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    estimated_candles: int | None = None

    def to_public(self) -> dict[str, Any]:
        req = self.request
        summary = {
            "symbol": req.get("symbol"),
            "market_type": req.get("market_type"),
            "interval": req.get("interval"),
            "start_ms": req.get("start_ms"),
            "end_ms": req.get("end_ms"),
            "risk_mode": req.get("risk_mode"),
            "data_source": req.get("data_source"),
            "initial_capital": req.get("initial_capital"),
        }
        out: dict[str, Any] = {
            "job_id": self.job_id,
            "status": self.status,
            "run_id": self.run_id,
            "created_ms": self.created_ms,
            "started_ms": self.started_ms,
            "finished_ms": self.finished_ms,
            "phase": self.phase,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "request_summary": summary,
            "dataset_hash": self.dataset_hash,
            "result_hash": self.result_hash,
            "performance_label": (
                "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
            ),
            "linear_limitation": (
                LINEAR_LIMITATION if req.get("market_type") == "linear" else None
            ),
        }
        return out


@dataclass
class RunLimits:
    max_candles: int = DEFAULT_MAX_CANDLES_PER_RUN
    max_range_ms: int = DEFAULT_MAX_RANGE_MS
    max_simultaneous: int = DEFAULT_MAX_SIMULTANEOUS_RUNS
    max_queued: int = DEFAULT_MAX_QUEUED_RUNS
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS


class BacktestRunService:
    """Process-local job registry with a single worker thread."""

    def __init__(
        self,
        *,
        results_dir: Path,
        limits: RunLimits | None = None,
    ) -> None:
        self.results_dir = Path(results_dir)
        self.jobs_dir = self.results_dir / "jobs"
        # Always nest datasets under the configured results root (never arbitrary paths).
        self.datasets_dir = self.results_dir / "datasets"
        self.limits = limits or RunLimits()
        self._lock = threading.RLock()
        self._jobs: dict[str, JobRecord] = {}
        self._by_idempotency: dict[str, str] = {}
        self._queue: list[str] = []
        self._running = 0
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._mark_interrupted_on_disk()

    def _mark_interrupted_on_disk(self) -> None:
        """On process start, RUNNING jobs from a prior crash become INTERRUPTED."""
        if not self.jobs_dir.exists():
            return
        for path in self.jobs_dir.glob(f"{JOB_ID_PREFIX}*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("status") in {"QUEUED", "RUNNING"}:
                data["status"] = "INTERRUPTED"
                data["finished_ms"] = int(time.time() * 1000)
                data["error_code"] = "process_restart"
                data["error_message"] = (
                    "Process restarted while job was in progress — "
                    "incomplete report is not presented as completed."
                )
                data["phase"] = "interrupted"
                try:
                    atomic_write_text(path, json.dumps(data, indent=2, sort_keys=True))
                except OSError:
                    continue

    def _persist(self, job: JobRecord) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self.jobs_dir / f"{job.job_id}.json"
        atomic_write_text(path, json.dumps(asdict(job), indent=2, sort_keys=True))

    def _ensure_worker(self) -> None:
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="cryptonova-backtest-worker",
            daemon=True,
        )
        self._worker.start()

    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            job_id: str | None = None
            with self._lock:
                if self._running >= self.limits.max_simultaneous:
                    job_id = None
                elif self._queue:
                    job_id = self._queue.pop(0)
                    self._running += 1
            if job_id is None:
                self._wake.wait(timeout=0.5)
                self._wake.clear()
                continue
            try:
                self._execute_job(job_id)
            finally:
                with self._lock:
                    self._running = max(0, self._running - 1)
                self._wake.set()

    def submit(self, body: BacktestRunRequest) -> tuple[JobRecord, bool]:
        """Validate + enqueue. Returns (job, idempotent_replay)."""
        self._validate_request(body)
        est = estimate_candle_count(body.start_ms, body.end_ms, body.interval)
        idem = body.idempotency_key
        with self._lock:
            if idem and idem in self._by_idempotency:
                existing = self._jobs.get(self._by_idempotency[idem])
                if existing is not None:
                    return existing, True
            queued = sum(1 for j in self._jobs.values() if j.status == "QUEUED")
            running = sum(1 for j in self._jobs.values() if j.status == "RUNNING")
            if queued >= self.limits.max_queued:
                raise RunServiceError(
                    "queue_full",
                    f"max queued runs ({self.limits.max_queued}) reached",
                    http_status=429,
                )
            if running + queued >= self.limits.max_simultaneous + self.limits.max_queued:
                raise RunServiceError(
                    "concurrency_limit",
                    "too many active/queued backtests",
                    http_status=429,
                )
            job_id = f"{JOB_ID_PREFIX}{uuid.uuid4().hex[:16]}"
            job = JobRecord(
                job_id=job_id,
                status="QUEUED",
                created_ms=int(time.time() * 1000),
                request=body.model_dump(),
                idempotency_key=idem,
                phase="queued",
                estimated_candles=est,
            )
            self._jobs[job_id] = job
            if idem:
                self._by_idempotency[idem] = job_id
            self._queue.append(job_id)
            self._persist(job)
            self._ensure_worker()
            self._wake.set()
            return job, False

    def get_job(self, job_id: str) -> JobRecord:
        jid = (job_id or "").strip()
        if not jid.startswith(JOB_ID_PREFIX) or len(jid) > 48:
            raise RunServiceError("invalid_job_id", "invalid job_id", http_status=400)
        with self._lock:
            job = self._jobs.get(jid)
            if job is not None:
                return job
        # Disk fallback (after restart).
        path = self.jobs_dir / f"{jid}.json"
        if not path.exists():
            raise RunServiceError("job_not_found", "job not found", http_status=404)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            job = JobRecord(**{k: data.get(k) for k in JobRecord.__dataclass_fields__})
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            raise RunServiceError("corrupt_job", "job record unreadable", http_status=422) from exc
        with self._lock:
            self._jobs[jid] = job
        return job

    def _validate_request(self, body: BacktestRunRequest) -> None:
        if body.data_source not in RUN_UI_DATA_SOURCES:
            raise RunServiceError("unsupported_data_source", "unsupported data_source")
        if body.risk_mode not in RUN_UI_RISK_MODES:
            raise RunServiceError("unsupported_risk_mode", "unsupported risk_mode")
        if body.data_source == "offline_fixture":
            if not body.dataset_hash:
                raise RunServiceError(
                    "dataset_hash_required",
                    "offline_fixture requires dataset_hash (content-addressed cache key)",
                )
        try:
            validate_history_request(
                symbol=body.symbol,
                market_type=body.market_type,
                interval=body.interval,
                start_ms=body.start_ms,
                end_ms=body.end_ms,
                max_candles=self.limits.max_candles,
                max_range_ms=self.limits.max_range_ms,
                require_ui_allowlist=True,
            )
        except HistoryProviderError as exc:
            raise RunServiceError(exc.code, exc.message) from exc
        if body.risk_mode == "portfolio" and body.market_type != "spot":
            raise RunServiceError(
                "invalid_risk_market",
                "portfolio risk mode requires market_type=spot",
            )
        # Decimal field sanity
        for name in ("initial_capital", "fee_rate", "slippage_bps"):
            try:
                val = Decimal(str(getattr(body, name)))
            except (InvalidOperation, ValueError) as exc:
                raise RunServiceError("invalid_decimal", f"{name} is not a valid decimal") from exc
            if name == "initial_capital" and val <= 0:
                raise RunServiceError("invalid_capital", "initial_capital must be positive")
            if name in {"fee_rate", "slippage_bps"} and val < 0:
                raise RunServiceError("invalid_fee", f"{name} must be non-negative")

    def _execute_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "RUNNING"
            job.started_ms = int(time.time() * 1000)
            job.phase = "loading_data"
            self._persist(job)
            req = dict(job.request)

        deadline = time.monotonic() + self.limits.max_runtime_seconds
        try:
            candles = None
            provenance = None
            dataset_hash = req.get("dataset_hash")

            if req["data_source"] == "offline_fixture":
                cached = load_dataset_cache(
                    str(dataset_hash),
                    datasets_dir=self.datasets_dir,
                    expected={
                        "symbol": req["symbol"],
                        "interval": req["interval"],
                        "market_type": req["market_type"],
                    },
                )
                candles = list(cached.candles)
                provenance = str(
                    cached.meta.get("provenance") or "OFFLINE HISTORICAL FIXTURE"
                )
                dataset_hash = cached.content_hash
            else:
                # Prefer cache hit when hash supplied; else fetch public history.
                if dataset_hash:
                    try:
                        cached = load_dataset_cache(
                            str(dataset_hash),
                            datasets_dir=self.datasets_dir,
                            expected={
                                "symbol": req["symbol"],
                                "interval": req["interval"],
                                "market_type": req["market_type"],
                            },
                        )
                        candles = list(cached.candles)
                        provenance = str(
                            cached.meta.get("provenance")
                            or "HISTORICAL BYBIT PUBLIC MARKET DATA (cache)"
                        )
                        dataset_hash = cached.content_hash
                    except DatasetCacheError:
                        candles = None

                if candles is None:
                    with self._lock:
                        job = self._jobs[job_id]
                        job.phase = "fetching_public_history"
                        self._persist(job)
                    if time.monotonic() > deadline:
                        raise RunServiceError("runtime_exceeded", "runtime limit before fetch")
                    transport = HttpxHistoryTransport()
                    try:
                        fetched = fetch_historical_candles(
                            transport,
                            symbol=req["symbol"],
                            market_type=req["market_type"],
                            interval=req["interval"],
                            start_ms=int(req["start_ms"]),
                            end_ms=int(req["end_ms"]),
                            grace_ms=int(req.get("grace_ms") or 2000),
                            max_candles=self.limits.max_candles,
                            max_range_ms=self.limits.max_range_ms,
                        )
                    finally:
                        transport.close()
                    from agent.backtest.dataset_cache import save_dataset_cache

                    saved = save_dataset_cache(
                        fetched.candles,
                        meta={
                            "symbol": fetched.symbol,
                            "market_type": fetched.market_type,
                            "interval": fetched.interval,
                            "start_ms": fetched.start_ms,
                            "end_ms": fetched.end_ms,
                            "provenance": fetched.provenance,
                            "retrieved_ms": fetched.retrieved_ms,
                            "page_count": fetched.page_count,
                            "source_kind": "bybit_public",
                            "label": fetched.provenance,
                            **fetched.meta,
                        },
                        datasets_dir=self.datasets_dir,
                    )
                    candles = list(fetched.candles)
                    provenance = fetched.provenance
                    dataset_hash = saved.content_hash

            if time.monotonic() > deadline:
                raise RunServiceError("runtime_exceeded", "runtime limit before replay")

            with self._lock:
                job = self._jobs[job_id]
                job.phase = "replaying_pipeline"
                job.dataset_hash = dataset_hash
                self._persist(job)

            cfg = BacktestConfig(
                symbol=str(req["symbol"]),
                market_type=str(req["market_type"]),
                interval=str(req["interval"]),
                start_ms=int(req["start_ms"]),
                end_ms=int(req["end_ms"]),
                initial_capital=Decimal(str(req["initial_capital"])),
                fee_rate=Decimal(str(req["fee_rate"])),
                slippage_bps=Decimal(str(req["slippage_bps"])),
                risk_mode=RiskMode(str(req["risk_mode"])),
                grace_ms=int(req.get("grace_ms") or 2000),
                data_source=(
                    DataSourceKind.BYBIT_PUBLIC
                    if req["data_source"] == "bybit_public"
                    else DataSourceKind.FIXTURE_FILE
                ),
                dataset_hash=dataset_hash,
            )
            # Pass candles explicitly so runner does not re-fetch.
            journal_dir = self.results_dir / "journals"
            result = run_backtest(cfg, candles=candles, journal_dir=journal_dir)
            # Annotate provenance if runner used caller_inline.
            if provenance and result.dataset.provenance == "caller_inline":
                # Rebuild public dict via persist; mutate extras only.
                pass
            persist_run_artifact(result, results_dir=self.results_dir)

            # Patch artifact dataset provenance label when caller_inline.
            if provenance:
                report_path = self.results_dir / f"{result.run_id}_report.json"
                if report_path.exists():
                    payload = json.loads(report_path.read_text(encoding="utf-8"))
                    ds = payload.get("dataset") or {}
                    if isinstance(ds, dict) and ds.get("provenance") == "caller_inline":
                        ds["provenance"] = provenance
                        if req["data_source"] == "bybit_public":
                            ds["source_kind"] = "bybit_public"
                        elif req["data_source"] == "offline_fixture":
                            ds["source_kind"] = "fixture_file"
                        payload["dataset"] = ds
                        atomic_write_text(
                            report_path, json.dumps(payload, indent=2, sort_keys=True)
                        )

            terminal = "COMPLETED"
            if result.status is BacktestStatus.FAILED:
                terminal = "FAILED"
            elif result.status is BacktestStatus.REJECTED_DATA:
                terminal = "FAILED"

            with self._lock:
                job = self._jobs[job_id]
                job.status = terminal
                job.finished_ms = int(time.time() * 1000)
                job.run_id = result.run_id
                job.dataset_hash = dataset_hash or result.dataset.content_hash
                job.result_hash = result.result_hash or None
                job.phase = "done"
                if terminal == "FAILED":
                    job.error_code = result.status.value
                    job.error_message = result.error or "backtest failed"
                self._persist(job)

        except (HistoryProviderError, DatasetCacheError, RunServiceError) as exc:
            code = getattr(exc, "code", "run_error")
            msg = getattr(exc, "message", str(exc))
            with self._lock:
                job = self._jobs[job_id]
                job.status = "FAILED"
                job.finished_ms = int(time.time() * 1000)
                job.phase = "failed"
                job.error_code = code
                job.error_message = msg
                self._persist(job)
        except Exception as exc:  # noqa: BLE001
            with self._lock:
                job = self._jobs[job_id]
                job.status = "FAILED"
                job.finished_ms = int(time.time() * 1000)
                job.phase = "failed"
                job.error_code = "internal_error"
                job.error_message = str(exc)
                self._persist(job)


_SERVICE: BacktestRunService | None = None
_SERVICE_LOCK = threading.Lock()


def get_run_service(results_dir: Path, limits: RunLimits | None = None) -> BacktestRunService:
    global _SERVICE
    root = Path(results_dir).resolve()
    with _SERVICE_LOCK:
        if _SERVICE is None or Path(_SERVICE.results_dir).resolve() != root:
            if _SERVICE is not None:
                _SERVICE._stop.set()
                _SERVICE._wake.set()
            _SERVICE = BacktestRunService(results_dir=root, limits=limits)
        elif limits is not None:
            _SERVICE.limits = limits
        return _SERVICE


def reset_run_service_for_tests() -> None:
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is not None:
            _SERVICE._stop.set()
            _SERVICE._wake.set()
        _SERVICE = None


def request_fingerprint(body: BacktestRunRequest) -> str:
    raw = json.dumps(body.model_dump(exclude={"idempotency_key"}), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
