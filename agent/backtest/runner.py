"""Backtest orchestration — isolated paper journal + SignalPipeline replay."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from agent.backtest.config import (
    PERFORMANCE_LABEL,
    BacktestConfig,
    DataSourceKind,
    effective_config_hash,
)
from agent.backtest.data import build_dataset, load_fixture_file, synthetic_trend_candles
from agent.backtest.dataset_cache import DatasetCacheError, load_dataset_cache, save_dataset_cache
from agent.backtest.execution_adapter import (
    is_actionable,
    process_market_candle,
    submit_decision,
)
from agent.backtest.history_provider import (
    HistoryProviderError,
    HttpxHistoryTransport,
    fetch_historical_candles,
)
from agent.backtest.metrics import collect_analytics, final_account_snapshot
from agent.backtest.models import (
    BacktestResult,
    BacktestStatus,
    DecisionCounters,
    DecisionRecord,
    ExecutionRecord,
)
from agent.backtest.pipeline_adapter import evaluate_at_index, make_pipeline
from agent.backtest.report import compute_result_hash
from agent.backtest.risk_adapter import build_broker, portfolio_enabled
from agent.backtest.store import isolated_journal_path, open_isolated_paper_store
from agent.backtest.validation import CandleValidationError
from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig
from agent.multi_agent.types import DecisionAction


def _count_action(counters: DecisionCounters, action: DecisionAction) -> None:
    if action is DecisionAction.BUY:
        counters.buy += 1
    elif action is DecisionAction.SELL:
        counters.sell += 1
    elif action is DecisionAction.HOLD:
        counters.hold += 1
    elif action is DecisionAction.BLOCKED:
        counters.blocked += 1


def _load_candles(config: BacktestConfig, candles: list[Candle] | None) -> tuple[list[Candle], str]:
    if candles is not None:
        return candles, "caller_inline"
    if config.data_source is DataSourceKind.FIXTURE_FILE:
        if not config.dataset_path:
            raise ValueError("dataset_path required for fixture_file source")
        loaded, meta = load_fixture_file(config.dataset_path)
        return loaded, str(meta.get("provenance") or f"fixture_file:{config.dataset_path}")
    if config.data_source is DataSourceKind.INLINE:
        return synthetic_trend_candles(), "synthetic_inline_generator"
    if config.data_source is DataSourceKind.BYBIT_PUBLIC:
        # Prefer integrity-checked local cache when dataset_hash is provided.
        if config.dataset_hash and config.dataset_path is None:
            try:
                cached = load_dataset_cache(
                    config.dataset_hash,
                    expected={
                        "symbol": config.symbol,
                        "interval": config.interval,
                        "market_type": config.market_type,
                    },
                )
                return list(cached.candles), str(
                    cached.meta.get("provenance") or "HISTORICAL BYBIT PUBLIC MARKET DATA (cache)"
                )
            except DatasetCacheError:
                pass
        if config.start_ms is None or config.end_ms is None:
            raise ValueError("start_ms and end_ms required for bybit_public source")
        transport = HttpxHistoryTransport()
        try:
            fetched = fetch_historical_candles(
                transport,
                symbol=config.symbol,
                market_type=config.market_type,
                interval=config.interval,
                start_ms=int(config.start_ms),
                end_ms=int(config.end_ms),
                grace_ms=config.grace_ms,
            )
        except HistoryProviderError as exc:
            raise CandleValidationError(exc.code, exc.message) from exc
        finally:
            transport.close()
        try:
            save_dataset_cache(
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
                    "source_kind": DataSourceKind.BYBIT_PUBLIC.value,
                    "label": fetched.provenance,
                    **fetched.meta,
                },
            )
        except DatasetCacheError:
            # Cache write failure must not block a valid fetch.
            pass
        return list(fetched.candles), fetched.provenance
    raise ValueError(f"unsupported data_source={config.data_source}")


def run_backtest(
    config: BacktestConfig | None = None,
    *,
    candles: list[Candle] | None = None,
    journal_dir: str | Path | None = None,
    journal_path: str | Path | None = None,
) -> BacktestResult:
    """
    Replay confirmed historical candles through SignalPipeline + isolated PaperBroker.

    Does not flip PAPER_* / AGENT_ALLOW_LIVE globals.
    Does not write to the operator paper journal or remote SoT.
    """
    cfg = config or BacktestConfig()
    created_ms = int(time.time() * 1000)
    run_id = f"bt_{uuid.uuid4().hex[:16]}"
    warnings: list[str] = []

    try:
        raw_candles, provenance = _load_candles(cfg, candles)
        identity, report = build_dataset(
            raw_candles,
            symbol=cfg.symbol,
            interval=cfg.interval,
            market_type=cfg.market_type,
            provenance=provenance,
            source_kind=cfg.data_source.value,
            start_ms=cfg.start_ms,
            end_ms=cfg.end_ms,
            allow_gaps=True,
        )
    except CandleValidationError as exc:
        empty_cfg = cfg.to_effective_dict(dataset_hash="invalid")
        return BacktestResult(
            run_id=run_id,
            status=BacktestStatus.REJECTED_DATA,
            performance_label=PERFORMANCE_LABEL,
            effective_config=empty_cfg,
            dataset=identity_placeholder(cfg, str(exc)),
            session_id=None,
            journal_path=None,
            eligible_candles=0,
            warm_up_candles=0,
            counters=DecisionCounters().as_dict(),
            decisions=(),
            executions=(),
            analytics=None,
            open_positions=0,
            final_available_balance=None,
            final_reserved_capital=None,
            final_marked_equity=None,
            data_quality_warnings=(exc.message,),
            result_hash="",
            created_ms=created_ms,
            error=f"{exc.code}:{exc.message}",
        )

    warnings.extend(report.warnings)
    series = list(report.candles)
    dataset_hash = identity.content_hash
    effective = cfg.to_effective_dict(dataset_hash=dataset_hash)
    effective["config_hash"] = effective_config_hash(effective)

    min_bars = cfg.effective_min_bars()
    pipe_cfg = SignalPipelineConfig(
        weights=cfg.pipeline.weights,
        risk=cfg.pipeline.risk,
        strategy_version=cfg.pipeline.strategy_version,
        min_confirmed_bars=min_bars,
        buy_threshold=cfg.pipeline.buy_threshold,
        sell_threshold=cfg.pipeline.sell_threshold,
        min_market_quality=cfg.pipeline.min_market_quality,
    )
    # Align paper risk balance with backtest capital for consistent sizing.
    from dataclasses import replace

    pipe_cfg = replace(
        pipe_cfg,
        risk=replace(pipe_cfg.risk, paper_balance=float(cfg.initial_capital)),
    )

    if len(series) < min_bars:
        warnings.append(
            f"insufficient_warmup: have {len(series)} bars, need {min_bars} — "
            "evaluations will remain data-insufficient"
        )

    jpath = Path(journal_path) if journal_path is not None else isolated_journal_path(journal_dir)
    store = open_isolated_paper_store(jpath)
    broker = build_broker(store, cfg)
    pipeline = make_pipeline(pipe_cfg)

    first_start = int(series[0].start)
    session = broker.create_session(now_ms=first_start, session_id=f"bts_{run_id}")
    session_id = session.session_id

    counters = DecisionCounters()
    decisions: list[DecisionRecord] = []
    executions: list[ExecutionRecord] = []
    use_portfolio = portfolio_enabled(cfg)

    warm_up = min(min_bars - 1, len(series)) if min_bars > 0 else 0
    eligible = 0

    try:
        for i, candle in enumerate(series):
            # 1) Advance broker with confirmed bar (fills prior signals; SL/TP).
            results = process_market_candle(
                broker,
                session_id=session_id,
                candle=candle,
                symbol=cfg.symbol,
                interval=cfg.interval,
            )
            for r in results:
                reason = r.reason or ""
                kind = "process"
                if reason.startswith("FILLED") or reason.startswith("CLOSED_"):
                    kind = "fill"
                    if r.ok:
                        counters.filled += 1
                executions.append(
                    ExecutionRecord(
                        candle_start_ms=int(candle.start),
                        kind=kind,
                        ok=bool(r.ok),
                        reason=reason,
                        order_id=r.order_id,
                        detail=dict(r.detail or {}),
                    )
                )

            # 2) Evaluate agents only once the bar is confirmed and warm-up satisfied.
            if i + 1 < min_bars:
                continue

            eligible += 1
            decision, now_ms = evaluate_at_index(
                pipeline,
                candles=series,
                index=i,
                symbol=cfg.symbol,
                category=cfg.market_type,
                interval=cfg.interval,
                grace_ms=cfg.grace_ms,
            )
            counters.evaluations += 1
            _count_action(counters, decision.action)
            decisions.append(
                DecisionRecord(
                    candle_start_ms=int(candle.start),
                    now_ms=now_ms,
                    action=decision.action.value,
                    risk_verdict=decision.risk.verdict.value,
                    decision_id=decision.decision_id,
                    signal_strength=float(decision.signal_strength),
                    reason_codes=tuple(decision.reason_codes),
                    entry=decision.levels.entry,
                    stop_loss=decision.levels.stop_loss,
                    take_profit=decision.levels.take_profit,
                    position_notional=decision.risk.position_notional,
                    contribution_biases=tuple(c.bias for c in decision.contributions),
                )
            )

            if not is_actionable(decision):
                continue

            submit = submit_decision(
                broker,
                session_id=session_id,
                decision=decision,
                signal_candle_start_ms=int(candle.start),
                use_portfolio_path=use_portfolio,
            )
            counters.submitted += 1
            if not submit.ok:
                counters.rejected += 1
            executions.append(
                ExecutionRecord(
                    candle_start_ms=int(candle.start),
                    kind="submit",
                    ok=bool(submit.ok),
                    reason=submit.reason or "",
                    order_id=submit.order_id,
                    detail=dict(submit.detail or {}),
                )
            )

        analytics = collect_analytics(journal_path=jpath, session_id=session_id)
        if analytics.get("data_quality_warnings"):
            warnings.extend(list(analytics["data_quality_warnings"]))
        snap = final_account_snapshot(store, session_id)
        opens = store.get_open_positions(session_id)

        draft = BacktestResult(
            run_id=run_id,
            status=BacktestStatus.COMPLETED,
            performance_label=PERFORMANCE_LABEL,
            effective_config=effective,
            dataset=identity,
            session_id=session_id,
            journal_path=str(jpath),
            eligible_candles=eligible,
            warm_up_candles=warm_up,
            counters=counters.as_dict(),
            decisions=tuple(decisions),
            executions=tuple(executions),
            analytics=analytics,
            open_positions=len(opens),
            final_available_balance=snap["available_balance"],
            final_reserved_capital=snap["reserved_capital"],
            final_marked_equity=snap["marked_equity"],
            data_quality_warnings=tuple(dict.fromkeys(warnings)),
            result_hash="",
            created_ms=created_ms,
            extras={
                "safety": {
                    "paper_broker_auto_attach": False,
                    "paper_portfolio_risk_enabled_global": False,
                    "agent_allow_live": False,
                    "isolated_journal": True,
                    "no_force_close_at_end": True,
                }
            },
        )
        return BacktestResult(
            run_id=draft.run_id,
            status=draft.status,
            performance_label=draft.performance_label,
            effective_config=draft.effective_config,
            dataset=draft.dataset,
            session_id=draft.session_id,
            journal_path=draft.journal_path,
            eligible_candles=draft.eligible_candles,
            warm_up_candles=draft.warm_up_candles,
            counters=draft.counters,
            decisions=draft.decisions,
            executions=draft.executions,
            analytics=draft.analytics,
            open_positions=draft.open_positions,
            final_available_balance=draft.final_available_balance,
            final_reserved_capital=draft.final_reserved_capital,
            final_marked_equity=draft.final_marked_equity,
            data_quality_warnings=draft.data_quality_warnings,
            result_hash=compute_result_hash(draft),
            created_ms=draft.created_ms,
            extras=draft.extras,
        )
    except Exception as exc:  # noqa: BLE001 — surface as failed run
        return BacktestResult(
            run_id=run_id,
            status=BacktestStatus.FAILED,
            performance_label=PERFORMANCE_LABEL,
            effective_config=effective,
            dataset=identity,
            session_id=session_id,
            journal_path=str(jpath),
            eligible_candles=eligible,
            warm_up_candles=warm_up,
            counters=counters.as_dict(),
            decisions=tuple(decisions),
            executions=tuple(executions),
            analytics=None,
            open_positions=0,
            final_available_balance=None,
            final_reserved_capital=None,
            final_marked_equity=None,
            data_quality_warnings=tuple(dict.fromkeys(warnings)),
            result_hash="",
            created_ms=created_ms,
            error=str(exc),
        )


def identity_placeholder(cfg: BacktestConfig, err: str):
    from agent.backtest.models import DatasetIdentity

    return DatasetIdentity(
        symbol=cfg.symbol,
        interval=cfg.interval,
        market_type=cfg.market_type,
        candle_count=0,
        first_start_ms=0,
        last_start_ms=0,
        content_hash="invalid",
        provenance=f"rejected:{err}",
        source_kind=cfg.data_source.value,
        warnings=(err,),
    )
