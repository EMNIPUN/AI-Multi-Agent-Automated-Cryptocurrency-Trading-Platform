"""Read-only helpers over saved 68A JSON report artifacts."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from agent.backtest.artifacts import (
    ArtifactError,
    default_results_dir,
    list_report_paths,
    load_run_payload,
)
from apps.api.app.backtests.schemas import (
    BacktestDecisionsResponse,
    BacktestEquityResponse,
    BacktestMetricsResponse,
    BacktestOrdersResponse,
    BacktestRunDetailResponse,
    BacktestRunListResponse,
    BacktestRunSummary,
    BacktestStatusResponse,
    BacktestTradesResponse,
)

ASSUMPTIONS = [
    "Spot-like unleveraged long-only simulation",
    "No leverage, short selling, funding, or liquidation modeling",
    "Next-candle open entry eligibility (65A)",
    "Configurable trading fees and adverse slippage",
    "Same-bar SL/TP: stop-loss first (conservative)",
    "Gap-through-stop: executable at candle open + adverse slippage",
    "No look-ahead: agents see confirmed bars through N only",
    "Snapshot-based observed drawdown (not true intraperiod max)",
    "Open positions are not force-closed at dataset end",
    "Backtest-only cash-cap may shrink signal-risk notionals to spendable cash",
    "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE",
]


def resolve_results_dir(configured: str | None) -> Path:
    if configured and configured.strip():
        return Path(configured.strip()).expanduser()
    return default_results_dir()


def dataset_label(dataset: dict[str, Any] | None, config: dict[str, Any] | None) -> str:
    ds = dataset or {}
    cfg = config or {}
    source = str(ds.get("source_kind") or cfg.get("data_source") or "").lower()
    provenance = str(ds.get("provenance") or "").lower()
    if "synthetic" in provenance or source == "inline":
        return "SYNTHETIC TEST DATA"
    if source == "bybit_public" or "bybit public" in provenance:
        return "HISTORICAL BYBIT PUBLIC MARKET DATA"
    if "offline historical" in provenance or (
        source == "fixture_file" and "historical" in provenance and "synthetic" not in provenance
    ):
        return "OFFLINE HISTORICAL FIXTURE"
    if source == "fixture_file" or "fixture" in provenance:
        # Distinguish unlabeled fixtures from synthetic generators.
        if "synthetic" in provenance:
            return "SYNTHETIC TEST DATA"
        return "OFFLINE HISTORICAL FIXTURE"
    if "historical" in provenance or "exchange" in provenance:
        return "HISTORICAL BYBIT PUBLIC MARKET DATA"
    if provenance:
        return f"OFFLINE FIXTURE ({ds.get('provenance')})"
    return "UNKNOWN DATASET PROVENANCE"


def build_status(
    *,
    enabled: bool,
    results_dir: Path,
    run_api_enabled: bool = False,
) -> BacktestStatusResponse:
    exists = results_dir.exists() and results_dir.is_dir()
    count = 0
    if enabled and exists:
        try:
            count = len(list_report_paths(results_dir))
        except ArtifactError:
            count = 0
    return BacktestStatusResponse(
        enabled=enabled,
        results_dir=str(results_dir),
        results_dir_exists=exists,
        run_count=count,
        run_api_enabled=run_api_enabled,
        mutations=False,
        runs_backtests=False,
    )


def _summary_from_payload(data: dict[str, Any]) -> BacktestRunSummary:
    ds = data.get("dataset") if isinstance(data.get("dataset"), dict) else {}
    cfg = data.get("effective_config") if isinstance(data.get("effective_config"), dict) else {}
    analytics = data.get("analytics") if isinstance(data.get("analytics"), dict) else {}
    return BacktestRunSummary(
        run_id=str(data.get("run_id") or ""),
        status=str(data.get("status") or "unknown"),
        symbol=ds.get("symbol") or cfg.get("symbol"),
        market_type=ds.get("market_type") or cfg.get("market_type"),
        interval=ds.get("interval") or cfg.get("interval"),
        first_start_ms=ds.get("first_start_ms"),
        last_start_ms=ds.get("last_start_ms"),
        candle_count=ds.get("candle_count"),
        provenance=ds.get("provenance"),
        source_kind=ds.get("source_kind"),
        dataset_label=dataset_label(ds, cfg),
        engine_version=cfg.get("engine_version"),
        pipeline_version=cfg.get("agent_pipeline_version"),
        dataset_hash=ds.get("content_hash") or cfg.get("dataset_hash"),
        result_hash=data.get("result_hash"),
        created_ms=data.get("created_ms"),
        closed_trades=analytics.get("closed_trades"),
        open_positions=data.get("open_positions"),
        net_realized_pnl=(
            str(analytics["net_realized_pnl"])
            if analytics.get("net_realized_pnl") is not None
            else None
        ),
        performance_label=data.get("performance_label"),
    )


def list_runs(
    results_dir: Path, *, limit: int, offset: int
) -> BacktestRunListResponse:
    paths = list_report_paths(results_dir)
    total = len(paths)
    items: list[BacktestRunSummary] = []
    for path in paths[offset : offset + limit]:
        try:
            data = load_run_payload(results_dir, path.name[: -len("_report.json")])
            items.append(_summary_from_payload(data))
        except ArtifactError:
            # Skip corrupt entries rather than failing the whole list.
            continue
    return BacktestRunListResponse(items=items, total=total, limit=limit, offset=offset)


def run_detail(results_dir: Path, run_id: str) -> BacktestRunDetailResponse:
    data = load_run_payload(results_dir, run_id)
    ds = data.get("dataset") if isinstance(data.get("dataset"), dict) else {}
    cfg = data.get("effective_config") if isinstance(data.get("effective_config"), dict) else {}
    assumptions = list(ASSUMPTIONS)
    if str(ds.get("market_type") or cfg.get("market_type") or "").lower() == "linear":
        assumptions.insert(
            0,
            "LINEAR market candles do NOT make this a realistic Futures backtest — "
            "execution remains spot-like long-only.",
        )
    return BacktestRunDetailResponse(
        run_id=str(data.get("run_id") or run_id),
        status=str(data.get("status") or "unknown"),
        performance_label=str(
            data.get("performance_label")
            or "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
        ),
        effective_config=cfg,
        dataset=ds,
        dataset_label=dataset_label(ds, cfg),
        counters=data.get("counters") if isinstance(data.get("counters"), dict) else {},
        eligible_candles=data.get("eligible_candles"),
        warm_up_candles=data.get("warm_up_candles"),
        open_positions=data.get("open_positions"),
        final_available_balance=data.get("final_available_balance"),
        final_reserved_capital=data.get("final_reserved_capital"),
        final_marked_equity=data.get("final_marked_equity"),
        data_quality_warnings=list(data.get("data_quality_warnings") or []),
        result_hash=data.get("result_hash"),
        created_ms=data.get("created_ms"),
        error=data.get("error"),
        assumptions=assumptions,
        extras=data.get("extras") if isinstance(data.get("extras"), dict) else {},
    )


def run_metrics(results_dir: Path, run_id: str) -> BacktestMetricsResponse:
    data = load_run_payload(results_dir, run_id)
    analytics = data.get("analytics") if isinstance(data.get("analytics"), dict) else None
    warnings = list(data.get("data_quality_warnings") or [])
    if analytics and isinstance(analytics.get("data_quality_warnings"), list):
        warnings = list(dict.fromkeys([*warnings, *analytics["data_quality_warnings"]]))
    return BacktestMetricsResponse(
        run_id=str(data.get("run_id") or run_id),
        performance_label=str(
            data.get("performance_label")
            or "HISTORICAL SIMULATION — NOT LIVE OR FORWARD-TESTED PERFORMANCE"
        ),
        counters=data.get("counters") if isinstance(data.get("counters"), dict) else {},
        analytics=analytics,
        final_available_balance=data.get("final_available_balance"),
        final_reserved_capital=data.get("final_reserved_capital"),
        final_marked_equity=data.get("final_marked_equity"),
        open_positions=data.get("open_positions"),
        data_quality_warnings=warnings,
    )


def _paginate(items: list[Any], *, limit: int, offset: int) -> tuple[list[Any], int]:
    total = len(items)
    return items[offset : offset + limit], total


def run_trades(
    results_dir: Path, run_id: str, *, limit: int, offset: int
) -> BacktestTradesResponse:
    data = load_run_payload(results_dir, run_id)
    analytics = data.get("analytics") if isinstance(data.get("analytics"), dict) else {}
    trades = analytics.get("trades") if isinstance(analytics.get("trades"), list) else []
    opens = (
        analytics.get("open_position_summaries")
        if isinstance(analytics.get("open_position_summaries"), list)
        else []
    )
    page, total = _paginate([t for t in trades if isinstance(t, dict)], limit=limit, offset=offset)
    return BacktestTradesResponse(
        run_id=str(data.get("run_id") or run_id),
        items=page,
        open_positions=[o for o in opens if isinstance(o, dict)],
        total=total,
        limit=limit,
        offset=offset,
    )


def run_equity(results_dir: Path, run_id: str) -> BacktestEquityResponse:
    data = load_run_payload(results_dir, run_id)
    analytics = data.get("analytics") if isinstance(data.get("analytics"), dict) else {}
    curve = analytics.get("equity_curve") if isinstance(analytics.get("equity_curve"), dict) else {}
    warnings = list(data.get("data_quality_warnings") or [])
    if isinstance(analytics.get("data_quality_warnings"), list):
        warnings = list(dict.fromkeys([*warnings, *analytics["data_quality_warnings"]]))
    marked = curve.get("marked_equity") if isinstance(curve.get("marked_equity"), list) else []
    realized = (
        curve.get("realized_balance") if isinstance(curve.get("realized_balance"), list) else []
    )
    return BacktestEquityResponse(
        run_id=str(data.get("run_id") or run_id),
        marked_equity=[p for p in marked if isinstance(p, dict)],
        realized_balance=[p for p in realized if isinstance(p, dict)],
        note=curve.get("note") if isinstance(curve.get("note"), str) else None,
        data_quality_warnings=warnings,
    )


def _enrich_decisions(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Attach matching submit/fill evidence to each decision (same candle)."""
    decisions = data.get("decisions") if isinstance(data.get("decisions"), list) else []
    executions = data.get("executions") if isinstance(data.get("executions"), list) else []
    submits_by_ms: dict[int, list[dict[str, Any]]] = {}
    fills_by_order: dict[str, list[dict[str, Any]]] = {}
    for ex in executions:
        if not isinstance(ex, dict):
            continue
        kind = str(ex.get("kind") or "")
        ms = ex.get("candle_start_ms")
        if kind == "submit" and isinstance(ms, int):
            submits_by_ms.setdefault(ms, []).append(ex)
        if kind == "fill":
            oid = ex.get("order_id")
            if oid:
                fills_by_order.setdefault(str(oid), []).append(ex)

    out: list[dict[str, Any]] = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        row = dict(d)
        ms = d.get("candle_start_ms")
        submits = submits_by_ms.get(int(ms), []) if isinstance(ms, int) else []
        row["submits"] = [
            {
                "ok": s.get("ok"),
                "reason": s.get("reason"),
                "order_id": s.get("order_id"),
            }
            for s in submits
        ]
        order_ids = [str(s.get("order_id")) for s in submits if s.get("order_id")]
        related_fills = []
        for oid in order_ids:
            related_fills.extend(fills_by_order.get(oid, []))
        row["related_fills"] = [
            {
                "ok": f.get("ok"),
                "reason": f.get("reason"),
                "order_id": f.get("order_id"),
                "candle_start_ms": f.get("candle_start_ms"),
            }
            for f in related_fills
        ]
        # Honest limitation: contribution_biases only — not full agent payloads.
        biases = d.get("contribution_biases") or []
        row["agent_bias_summary"] = {
            "market": biases[0] if len(biases) > 0 else None,
            "trend": biases[1] if len(biases) > 1 else None,
            "momentum": biases[2] if len(biases) > 2 else None,
            "note": "Bias labels only; full agent assessments not persisted by 68A",
        }
        out.append(row)
    return out


def run_decisions(
    results_dir: Path, run_id: str, *, limit: int, offset: int
) -> BacktestDecisionsResponse:
    data = load_run_payload(results_dir, run_id)
    items = _enrich_decisions(data)
    page, total = _paginate(items, limit=limit, offset=offset)
    return BacktestDecisionsResponse(
        run_id=str(data.get("run_id") or run_id),
        items=page,
        total=total,
        limit=limit,
        offset=offset,
    )


def run_orders(
    results_dir: Path, run_id: str, *, limit: int, offset: int
) -> BacktestOrdersResponse:
    data = load_run_payload(results_dir, run_id)
    executions = data.get("executions") if isinstance(data.get("executions"), list) else []
    # Prefer submit records as "orders"; attach later fill reasons when present.
    submits = [e for e in executions if isinstance(e, dict) and e.get("kind") == "submit"]
    fills = [e for e in executions if isinstance(e, dict) and e.get("kind") == "fill"]
    fills_by_order: dict[str, list[dict[str, Any]]] = {}
    for f in fills:
        oid = f.get("order_id")
        if oid:
            fills_by_order.setdefault(str(oid), []).append(f)

    decisions = data.get("decisions") if isinstance(data.get("decisions"), list) else []
    decision_by_ms = {
        int(d["candle_start_ms"]): d
        for d in decisions
        if isinstance(d, dict) and isinstance(d.get("candle_start_ms"), int)
    }

    items: list[dict[str, Any]] = []
    reject_counter: Counter[str] = Counter()
    for s in submits:
        row = dict(s)
        oid = s.get("order_id")
        row["fills"] = fills_by_order.get(str(oid), []) if oid else []
        ms = s.get("candle_start_ms")
        if isinstance(ms, int) and ms in decision_by_ms:
            dec = decision_by_ms[ms]
            row["decision_id"] = dec.get("decision_id")
            row["decision_action"] = dec.get("action")
            row["decision_risk_verdict"] = dec.get("risk_verdict")
        if not s.get("ok"):
            reject_counter[str(s.get("reason") or "UNKNOWN")] += 1
        # Final status heuristic
        if s.get("ok") and row["fills"]:
            row["final_status"] = "filled"
        elif s.get("ok"):
            row["final_status"] = "accepted_pending_or_unfilled"
        else:
            row["final_status"] = "rejected"
        items.append(row)

    page, total = _paginate(items, limit=limit, offset=offset)
    return BacktestOrdersResponse(
        run_id=str(data.get("run_id") or run_id),
        items=page,
        total=total,
        limit=limit,
        offset=offset,
        rejection_breakdown=dict(reject_counter),
    )
