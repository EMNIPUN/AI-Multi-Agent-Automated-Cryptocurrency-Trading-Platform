"""Deterministic signals-only orchestration — no exchange writes.

LLM decision support is a separate post-evaluation service
(``agent.llm_intelligence``). This pipeline never calls it.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from dataclasses import replace
from pathlib import Path

from agent.market_data import Candle
from agent.multi_agent.config import SignalPipelineConfig
from agent.multi_agent.coordinator import coordinate
from agent.multi_agent.market_agent import build_market_snapshot
from agent.multi_agent.momentum_agent import evaluate_momentum
from agent.multi_agent.regime_agent import evaluate_regime
from agent.multi_agent.risk_agent import (
    SignalRiskState,
    evaluate_signal_risk,
    remember_approved_signal,
)
from agent.multi_agent.decision_payload import build_decision_sync_payload
from agent.multi_agent.signal_history_store import (
    CheckpointWrite,
    SignalHistoryStore,
    SignalHistoryStoreError,
)
from agent.multi_agent.structure_agent import evaluate_structure
from agent.multi_agent.trend_agent import evaluate_trend
from agent.multi_agent.volume_agent import evaluate_volume
from agent.multi_agent.types import (
    AgentContribution,
    CoordinatorDecision,
    DecisionAction,
    HypotheticalLevels,
    MarketCategoryKind,
    MarketSnapshot,
    RiskAssessment,
    RiskVerdict,
)


def _block_persist_failure(decision: CoordinatorDecision, reason: str) -> CoordinatorDecision:
    """Convert an actionable decision into BLOCKED when durable write fails."""
    risk = replace(
        decision.risk,
        verdict=RiskVerdict.VETO,
        reason_codes=tuple(dict.fromkeys((*decision.risk.reason_codes, "PERSISTENCE_FAILED"))),
        explanation=f"Persistence failed — fail closed ({reason})",
        position_notional=None,
    )
    return replace(
        decision,
        action=DecisionAction.BLOCKED,
        signal_strength=0.0,
        levels=HypotheticalLevels(None, None, None),
        risk=risk,
        reason_codes=tuple(dict.fromkeys((*decision.reason_codes, "PERSISTENCE_FAILED"))),
        explanation=f"Persistence failed — no actionable signal ({reason})",
        execution_allowed=False,
    )


class SignalPipeline:
    """
    Explicit order: Market → Trend/Momentum/Volume/Structure → Coordinator → Risk → finalize.

    Fail-closed on timeouts/errors/persistence. Never calls wallet or order endpoints.
    """

    def __init__(
        self,
        config: SignalPipelineConfig | None = None,
        risk_state: SignalRiskState | None = None,
        history_store: SignalHistoryStore | None = None,
        *,
        persist: bool = False,
        db_path: str | Path | None = None,
        require_persist: bool | None = None,
    ) -> None:
        self.config = config or SignalPipelineConfig()
        self.history_store = history_store
        if persist and self.history_store is None:
            self.history_store = SignalHistoryStore(db_path)
        # When a store is attached, durable writes are mandatory for actionable signals.
        self.require_persist = (
            bool(require_persist)
            if require_persist is not None
            else self.history_store is not None
        )
        if risk_state is not None:
            self.risk_state = risk_state
        elif self.history_store is not None:
            try:
                self.risk_state = self.history_store.load_risk_state()
            except SignalHistoryStoreError:
                self.risk_state = SignalRiskState(halted=True)
                try:
                    self.history_store.mark_risk_corrupt()
                except Exception:  # noqa: BLE001
                    pass
        else:
            self.risk_state = SignalRiskState()

    def evaluate(
        self,
        *,
        symbol: str,
        category: str,
        interval: str,
        candles: list[Candle],
        now_ms: int,
        data_path: str = "public_fixture",
        checkpoint: CheckpointWrite | None = None,
        news_advisory_enabled: bool = False,
        news_context=None,
        news_context_loader=None,
    ) -> CoordinatorDecision:
        timeout_s = max(0.05, self.config.risk.agent_timeout_ms / 1000.0)
        loaded_news = None
        if news_advisory_enabled:
            loaded_news = _load_news_context(
                symbol=symbol,
                now_ms=now_ms,
                news_context=news_context,
                news_context_loader=news_context_loader,
            )

        snap, market_contrib = build_market_snapshot(
            symbol=symbol,
            category=category,
            interval=interval,
            candles=candles,
            now_ms=now_ms,
            data_path=data_path,
            min_bars=min(50, self.config.min_confirmed_bars),
            news_context=loaded_news,
        )

        def _fail_closed(agent_id: str, *, timed_out: bool = False, error: str | None = None) -> AgentContribution:
            return AgentContribution(
                agent_id=agent_id,
                agent_version="6.0.0",
                bias="INSUFFICIENT_DATA",
                confidence=0.0,
                reason_codes=("AGENT_TIMEOUT",) if timed_out else ("AGENT_EXCEPTION",),
                explanation=(
                    f"{agent_id} agent timed out — fail closed"
                    if timed_out
                    else f"{agent_id} agent error — fail closed"
                ),
                timed_out=timed_out,
                error=error or ("timeout" if timed_out else None),
            )

        def _run_trend() -> AgentContribution:
            return evaluate_trend(snap, news_context=loaded_news)

        def _run_momentum() -> AgentContribution:
            return evaluate_momentum(snap, news_context=loaded_news)

        def _run_volume() -> AgentContribution:
            return evaluate_volume(snap)

        def _run_structure() -> AgentContribution:
            return evaluate_structure(snap)

        runners = {
            "trend": _run_trend,
            "momentum": _run_momentum,
            "volume": _run_volume,
            "structure": _run_structure,
        }
        results: dict[str, AgentContribution] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {name: pool.submit(fn) for name, fn in runners.items()}
            for name, fut in futures.items():
                try:
                    results[name] = fut.result(timeout=timeout_s)
                except FuturesTimeout:
                    results[name] = _fail_closed(name, timed_out=True)
                except Exception as exc:  # noqa: BLE001
                    results[name] = _fail_closed(name, error=type(exc).__name__)

        trend = results["trend"]
        momentum = results["momentum"]
        volume = results["volume"]
        structure = results["structure"]

        def _risk_fn(**kwargs):
            if news_advisory_enabled:
                kwargs["news_context"] = loaded_news
            return evaluate_signal_risk(**kwargs)

        decision = coordinate(
            snapshot=snap,
            market_contrib=market_contrib,
            trend=trend,
            momentum=momentum,
            volume=volume,
            structure=structure,
            config=self.config,
            risk_fn=_risk_fn,
            risk_state=self.risk_state,
            regime=evaluate_regime(
                snap, self.config.regime, max_atr_pct=self.config.risk.max_atr_pct
            ),
        )

        approved = (
            decision.action in {DecisionAction.BUY, DecisionAction.SELL}
            and decision.risk.verdict is RiskVerdict.APPROVED
        )

        if self.history_store is not None and self.require_persist:
            if approved:
                remember_approved_signal(
                    self.risk_state,
                    key=decision.idempotent_key,
                    now_ms=now_ms,
                )
            try:
                # Single SQLite TX: decision + risk + full outbox (+ optional checkpoint).
                self.history_store.persist_decision_and_risk(
                    decision,
                    self.risk_state,
                    now_ms=now_ms,
                    checkpoint=checkpoint,
                    outbox_payload=build_decision_sync_payload(decision),
                    enqueue_outbox=True,
                )
            except SignalHistoryStoreError as exc:
                # Reload durable risk so in-memory remember cannot drift.
                try:
                    self.risk_state = self.history_store.load_risk_state()
                except SignalHistoryStoreError:
                    self.risk_state = SignalRiskState(halted=True)
                    try:
                        self.history_store.mark_risk_corrupt()
                    except Exception:  # noqa: BLE001
                        pass
                if approved or decision.action in {
                    DecisionAction.BUY,
                    DecisionAction.SELL,
                }:
                    decision = _block_persist_failure(decision, type(exc).__name__)
                else:
                    # Non-actionable outcomes still must not pretend durability succeeded.
                    decision = _block_persist_failure(decision, type(exc).__name__)
        else:
            if approved:
                remember_approved_signal(
                    self.risk_state,
                    key=decision.idempotent_key,
                    now_ms=now_ms,
                )

        assert decision.execution_allowed is False
        if news_advisory_enabled:
            from agent.multi_agent.news_advisory import conflict_note, observation_from_context

            record = observation_from_context(loaded_news)
            record["technical_action"] = decision.action.value
            record["risk_verdict"] = decision.risk.verdict.value
            record["technical_news_conflict"] = conflict_note(decision.action.value, loaded_news)
            record["news_changed_decision"] = False
            decision = replace(decision, news_advisory=record, news_changed_decision=False)
        # Actionable directional signals are never returned without durable write when store attached.
        if (
            self.history_store is not None
            and self.require_persist
            and decision.action in {DecisionAction.BUY, DecisionAction.SELL}
        ):
            # Persist path above either succeeded or converted to BLOCKED.
            pass
        return decision


def _load_news_context(*, symbol: str, now_ms: int, news_context, news_context_loader):
    from agent.news.context_provider import unavailable_news_context
    from agent.news.schemas import ContextStatus

    try:
        if news_context is not None:
            return news_context
        if callable(news_context_loader):
            return news_context_loader()
        return unavailable_news_context(
            symbol,
            now_ms,
            "news_context_not_supplied",
            storage_availability="unavailable",
            status=ContextStatus.ERROR,
        )
    except Exception as exc:  # noqa: BLE001 — technical pipeline must continue
        return unavailable_news_context(
            symbol,
            now_ms,
            f"news_context_failed:{type(exc).__name__}",
            storage_availability="unavailable",
            status=ContextStatus.ERROR,
        )


def evaluate_signals(
    *,
    symbol: str,
    category: str,
    interval: str,
    candles: list[Candle],
    now_ms: int | None = None,
    data_path: str = "public_fixture",
    config: SignalPipelineConfig | None = None,
    risk_state: SignalRiskState | None = None,
    history_store: SignalHistoryStore | None = None,
    persist: bool = False,
    news_advisory_enabled: bool = False,
    news_context=None,
    news_context_loader=None,
) -> CoordinatorDecision:
    pipe = SignalPipeline(
        config=config,
        risk_state=risk_state,
        history_store=history_store,
        persist=persist,
    )
    return pipe.evaluate(
        symbol=symbol,
        category=category,
        interval=interval,
        candles=candles,
        now_ms=now_ms if now_ms is not None else int(time.time() * 1000),
        data_path=data_path,
        news_advisory_enabled=news_advisory_enabled,
        news_context=news_context,
        news_context_loader=news_context_loader,
    )


def blocked_shell(
    *,
    symbol: str,
    category: str,
    interval: str,
    now_ms: int,
    reason: str,
) -> CoordinatorDecision:
    """Fail-closed shell decision when upstream cannot even build candles."""
    snap = MarketSnapshot(
        symbol=symbol.upper(),
        category=MarketCategoryKind.LINEAR if category != "spot" else MarketCategoryKind.SPOT,
        interval=interval,
        candles=(),
        closes=(),
        volumes=(),
        newest_close_ms=0,
        as_of_ms=now_ms,
        data_fresh=False,
        data_path="unavailable",
        reason_codes=(reason,),
        valid=False,
    )
    risk = RiskAssessment(
        verdict=RiskVerdict.VETO,
        reason_codes=(reason,),
        explanation=reason,
        paper_balance=0.0,
        risk_fraction=0.0,
        position_notional=None,
        stop_distance_pct=None,
        reward_distance_pct=None,
        risk_reward=None,
    )
    return CoordinatorDecision(
        action=DecisionAction.BLOCKED,
        symbol=snap.symbol,
        category=snap.category.value,
        interval=interval,
        timestamp_ms=now_ms,
        strategy_version=SignalPipelineConfig().strategy_version,
        correlation_id="c_blocked",
        decision_id="dec_blocked",
        signal_strength=0.0,
        signal_strength_note="n/a",
        contributions=(),
        risk=risk,
        reason_codes=(reason,),
        explanation=reason,
        levels=HypotheticalLevels(None, None, None),
        market=snap,
        idempotent_key="idem_blocked",
        directional_conviction=0.0,
        market_quality=0.0,
        config_hash="",
        source_mode="SIMULATED",
        execution_allowed=False,
    )
