"""Offline calibration of coordinator weights/thresholds from labeled outcomes.

Fits a CalibrationProfile via coarse grid search. Never trains online.
Corrupt/missing profiles fail closed to default SignalPipelineConfig knobs.
Scores remain calibrated historical agreement — not guaranteed win probability.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Sequence

from agent.multi_agent.config import SignalAgentWeights, SignalPipelineConfig

SCORE_KIND = "calibrated_historical_agreement"
DEFAULT_PROFILE_DIR = Path("data/calibration")


@dataclass(frozen=True)
class LabeledOutcome:
    """One historical decision sample for offline fitting."""

    directional_conviction: float
    action: str  # BUY / SELL / HOLD / BLOCKED
    realized_pnl: float
    trend_sign: float = 0.0  # -1..1 optional agent signed scores
    momentum_sign: float = 0.0
    volume_sign: float = 0.0
    structure_sign: float = 0.0


@dataclass(frozen=True)
class CalibrationMetrics:
    sample_count: int
    trade_count: int
    hit_rate: float | None
    expectancy: float | None
    net_pnl: float
    max_drawdown: float | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationProfile:
    profile_id: str
    profile_hash: str
    strategy_version: str
    sample_count: int
    sample_window_start_ms: int | None
    sample_window_end_ms: int | None
    weights: SignalAgentWeights
    buy_threshold: float
    sell_threshold: float
    metrics: CalibrationMetrics
    score_kind: str = SCORE_KIND
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_hash": self.profile_hash,
            "strategy_version": self.strategy_version,
            "sample_count": self.sample_count,
            "sample_window_start_ms": self.sample_window_start_ms,
            "sample_window_end_ms": self.sample_window_end_ms,
            "weights": asdict(self.weights.normalized()),
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "metrics": self.metrics.to_dict(),
            "score_kind": self.score_kind,
            "notes": list(self.notes),
            "label": (
                "Calibrated historical agreement — not a guaranteed win probability"
            ),
        }

    @staticmethod
    def from_dict(payload: dict[str, Any]) -> CalibrationProfile:
        if not isinstance(payload, dict):
            raise CalibrationError("profile_not_object")
        weights_raw = payload.get("weights") or {}
        if not isinstance(weights_raw, dict):
            raise CalibrationError("weights_invalid")
        metrics_raw = payload.get("metrics") or {}
        if not isinstance(metrics_raw, dict):
            raise CalibrationError("metrics_invalid")
        try:
            weights = SignalAgentWeights(
                trend=float(weights_raw.get("trend", 0.4)),
                momentum=float(weights_raw.get("momentum", 0.3)),
                volume=float(weights_raw.get("volume", 0.15)),
                structure=float(weights_raw.get("structure", 0.15)),
            ).normalized()
            metrics = CalibrationMetrics(
                sample_count=int(metrics_raw.get("sample_count", 0)),
                trade_count=int(metrics_raw.get("trade_count", 0)),
                hit_rate=_opt_float(metrics_raw.get("hit_rate")),
                expectancy=_opt_float(metrics_raw.get("expectancy")),
                net_pnl=float(metrics_raw.get("net_pnl", 0.0)),
                max_drawdown=_opt_float(metrics_raw.get("max_drawdown")),
            )
            profile = CalibrationProfile(
                profile_id=str(payload["profile_id"]),
                profile_hash=str(payload["profile_hash"]),
                strategy_version=str(payload.get("strategy_version") or ""),
                sample_count=int(payload.get("sample_count") or metrics.sample_count),
                sample_window_start_ms=_opt_int(payload.get("sample_window_start_ms")),
                sample_window_end_ms=_opt_int(payload.get("sample_window_end_ms")),
                weights=weights,
                buy_threshold=float(payload["buy_threshold"]),
                sell_threshold=float(payload["sell_threshold"]),
                metrics=metrics,
                score_kind=str(payload.get("score_kind") or SCORE_KIND),
                notes=tuple(payload.get("notes") or ()),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CalibrationError(f"profile_parse_failed:{type(exc).__name__}") from exc
        expected = compute_profile_hash(profile)
        if profile.profile_hash != expected:
            raise CalibrationError("profile_hash_mismatch")
        return profile


class CalibrationError(Exception):
    """Fail-closed calibration errors."""


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def compute_profile_hash(profile: CalibrationProfile) -> str:
    payload = {
        "profile_id": profile.profile_id,
        "strategy_version": profile.strategy_version,
        "sample_count": profile.sample_count,
        "sample_window_start_ms": profile.sample_window_start_ms,
        "sample_window_end_ms": profile.sample_window_end_ms,
        "weights": asdict(profile.weights.normalized()),
        "buy_threshold": profile.buy_threshold,
        "sell_threshold": profile.sell_threshold,
        "metrics": profile.metrics.to_dict(),
        "score_kind": profile.score_kind,
        "notes": list(profile.notes),
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_metrics(outcomes: Sequence[LabeledOutcome]) -> CalibrationMetrics:
    trades = [o for o in outcomes if o.action in {"BUY", "SELL"} and o.realized_pnl is not None]
    pnls = [float(o.realized_pnl) for o in trades]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p < 0)
    trade_count = len(pnls)
    hit_rate = (wins / trade_count) if trade_count else None
    expectancy = (sum(pnls) / trade_count) if trade_count else None
    net = sum(pnls)
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return CalibrationMetrics(
        sample_count=len(outcomes),
        trade_count=trade_count,
        hit_rate=hit_rate,
        expectancy=expectancy,
        net_pnl=net,
        max_drawdown=max_dd if trade_count else None,
    )


def _simulate_action(
    conviction: float,
    *,
    buy_threshold: float,
    sell_threshold: float,
) -> str:
    if conviction >= buy_threshold:
        return "BUY"
    if conviction <= sell_threshold:
        return "SELL"
    return "HOLD"


def _reweight_conviction(sample: LabeledOutcome, weights: SignalAgentWeights) -> float:
    """Rebuild conviction from stored agent signs when available; else keep original."""
    w = weights.normalized()
    parts = (
        sample.trend_sign * w.trend
        + sample.momentum_sign * w.momentum
        + sample.volume_sign * w.volume
        + sample.structure_sign * w.structure
    )
    # If agent signs were not provided, fall back to recorded conviction.
    if all(
        abs(x) < 1e-12
        for x in (sample.trend_sign, sample.momentum_sign, sample.volume_sign, sample.structure_sign)
    ):
        return max(-1.0, min(1.0, sample.directional_conviction))
    return max(-1.0, min(1.0, parts))


def _score_params(
    outcomes: Sequence[LabeledOutcome],
    *,
    weights: SignalAgentWeights,
    buy_threshold: float,
    sell_threshold: float,
) -> CalibrationMetrics:
    simulated: list[LabeledOutcome] = []
    for sample in outcomes:
        conviction = _reweight_conviction(sample, weights)
        action = _simulate_action(
            conviction, buy_threshold=buy_threshold, sell_threshold=sell_threshold
        )
        # Only keep PnL when simulated action matches historical trade side,
        # otherwise treat as flat (0) — conservative offline estimate.
        pnl = float(sample.realized_pnl) if action == sample.action and sample.action in {"BUY", "SELL"} else 0.0
        if action in {"BUY", "SELL"} and sample.action not in {"BUY", "SELL"}:
            pnl = 0.0
        simulated.append(
            LabeledOutcome(
                directional_conviction=conviction,
                action=action if action in {"BUY", "SELL"} else "HOLD",
                realized_pnl=pnl if action in {"BUY", "SELL"} else 0.0,
                trend_sign=sample.trend_sign,
                momentum_sign=sample.momentum_sign,
                volume_sign=sample.volume_sign,
                structure_sign=sample.structure_sign,
            )
        )
    return compute_metrics(simulated)


def fit_calibration_profile(
    outcomes: Sequence[LabeledOutcome],
    *,
    strategy_version: str,
    profile_id: str = "offline_grid_v1",
    sample_window_start_ms: int | None = None,
    sample_window_end_ms: int | None = None,
    min_samples: int = 20,
) -> CalibrationProfile:
    if len(outcomes) < min_samples:
        raise CalibrationError("insufficient_samples")

    buy_grid = (0.25, 0.30, 0.35, 0.40, 0.45)
    sell_grid = (-0.25, -0.30, -0.35, -0.40, -0.45)
    weight_grid = (
        SignalAgentWeights(0.40, 0.30, 0.15, 0.15),
        SignalAgentWeights(0.45, 0.25, 0.15, 0.15),
        SignalAgentWeights(0.35, 0.25, 0.20, 0.20),
        SignalAgentWeights(0.30, 0.30, 0.20, 0.20),
        SignalAgentWeights(0.50, 0.30, 0.10, 0.10),
    )

    best_metrics: CalibrationMetrics | None = None
    best_weights = SignalAgentWeights()
    best_buy = 0.35
    best_sell = -0.35

    for weights in weight_grid:
        for buy in buy_grid:
            for sell in sell_grid:
                if buy <= 0 or sell >= 0 or buy < abs(sell) - 0.15:
                    continue
                metrics = _score_params(
                    outcomes,
                    weights=weights,
                    buy_threshold=buy,
                    sell_threshold=sell,
                )
                if best_metrics is None or _better(metrics, best_metrics):
                    best_metrics = metrics
                    best_weights = weights.normalized()
                    best_buy = buy
                    best_sell = sell

    assert best_metrics is not None
    draft = CalibrationProfile(
        profile_id=profile_id,
        profile_hash="",  # filled below
        strategy_version=strategy_version,
        sample_count=len(outcomes),
        sample_window_start_ms=sample_window_start_ms,
        sample_window_end_ms=sample_window_end_ms,
        weights=best_weights,
        buy_threshold=best_buy,
        sell_threshold=best_sell,
        metrics=best_metrics,
        notes=(
            "offline_grid_search",
            "fail_closed_on_corrupt_profile",
            SCORE_KIND,
        ),
    )
    digest = compute_profile_hash(draft)
    return replace(draft, profile_hash=digest)


def _better(candidate: CalibrationMetrics, incumbent: CalibrationMetrics) -> bool:
    """Prefer higher expectancy, then hit rate, then net pnl; require some trades."""
    if candidate.trade_count == 0 and incumbent.trade_count > 0:
        return False
    if incumbent.trade_count == 0 and candidate.trade_count > 0:
        return True
    c_exp = candidate.expectancy if candidate.expectancy is not None else -math.inf
    i_exp = incumbent.expectancy if incumbent.expectancy is not None else -math.inf
    if c_exp != i_exp:
        return c_exp > i_exp
    c_hit = candidate.hit_rate if candidate.hit_rate is not None else -1.0
    i_hit = incumbent.hit_rate if incumbent.hit_rate is not None else -1.0
    if c_hit != i_hit:
        return c_hit > i_hit
    return candidate.net_pnl > incumbent.net_pnl


def apply_calibration(
    config: SignalPipelineConfig,
    profile: CalibrationProfile | None,
) -> SignalPipelineConfig:
    """Return config with calibrated knobs, or unchanged defaults if profile is None."""
    if profile is None:
        return config
    expected = compute_profile_hash(profile)
    if profile.profile_hash != expected:
        raise CalibrationError("profile_hash_mismatch")
    return replace(
        config,
        weights=profile.weights.normalized(),
        buy_threshold=float(profile.buy_threshold),
        sell_threshold=float(profile.sell_threshold),
        calibration_profile_id=profile.profile_id,
        calibration_hash=profile.profile_hash,
        strategy_version=config.strategy_version,
    )


def save_profile(profile: CalibrationProfile, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
    return target


def load_profile(path: str | Path) -> CalibrationProfile:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CalibrationError("profile_missing") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise CalibrationError(f"profile_unreadable:{type(exc).__name__}") from exc
    return CalibrationProfile.from_dict(payload)


def load_profile_or_default(
    path: str | Path | None,
    config: SignalPipelineConfig,
) -> SignalPipelineConfig:
    """Fail closed: missing/corrupt profile → original config (no calibration)."""
    if not path:
        return config
    try:
        profile = load_profile(path)
        return apply_calibration(config, profile)
    except CalibrationError:
        return config


def compare_calibration_metrics(
    before: CalibrationMetrics | dict[str, Any],
    after: CalibrationMetrics | dict[str, Any],
) -> dict[str, Any]:
    b = before if isinstance(before, CalibrationMetrics) else CalibrationMetrics(**{
        "sample_count": int(before.get("sample_count", 0)),
        "trade_count": int(before.get("trade_count", 0)),
        "hit_rate": _opt_float(before.get("hit_rate")),
        "expectancy": _opt_float(before.get("expectancy")),
        "net_pnl": float(before.get("net_pnl", 0.0)),
        "max_drawdown": _opt_float(before.get("max_drawdown")),
    })
    a = after if isinstance(after, CalibrationMetrics) else CalibrationMetrics(**{
        "sample_count": int(after.get("sample_count", 0)),
        "trade_count": int(after.get("trade_count", 0)),
        "hit_rate": _opt_float(after.get("hit_rate")),
        "expectancy": _opt_float(after.get("expectancy")),
        "net_pnl": float(after.get("net_pnl", 0.0)),
        "max_drawdown": _opt_float(after.get("max_drawdown")),
    })
    return {
        "before": b.to_dict(),
        "after": a.to_dict(),
        "delta": {
            "trade_count": a.trade_count - b.trade_count,
            "hit_rate": None
            if a.hit_rate is None or b.hit_rate is None
            else a.hit_rate - b.hit_rate,
            "expectancy": None
            if a.expectancy is None or b.expectancy is None
            else a.expectancy - b.expectancy,
            "net_pnl": a.net_pnl - b.net_pnl,
            "max_drawdown": None
            if a.max_drawdown is None or b.max_drawdown is None
            else a.max_drawdown - b.max_drawdown,
        },
        "score_kind": SCORE_KIND,
        "label": "Before/after offline calibration comparison — not live edge guarantee",
    }


def outcomes_from_analytics_trades(
    trades: Iterable[dict[str, Any]],
    *,
    default_conviction: float = 0.4,
) -> list[LabeledOutcome]:
    """Best-effort mapping from paper/backtest trade dicts to labeled samples."""
    out: list[LabeledOutcome] = []
    for trade in trades:
        side = str(trade.get("side") or trade.get("action") or "").upper()
        if side in {"LONG", "BUY"}:
            action = "BUY"
        elif side in {"SHORT", "SELL"}:
            action = "SELL"
        else:
            continue
        pnl_raw = trade.get("net_realized_pnl", trade.get("realized_pnl", trade.get("pnl")))
        try:
            pnl = float(pnl_raw)
        except (TypeError, ValueError):
            continue
        conviction = _opt_float(trade.get("directional_conviction"))
        if conviction is None:
            conviction = default_conviction if action == "BUY" else -default_conviction
        out.append(
            LabeledOutcome(
                directional_conviction=float(conviction),
                action=action,
                realized_pnl=pnl,
                trend_sign=float(_opt_float(trade.get("trend_sign")) or conviction),
                momentum_sign=float(_opt_float(trade.get("momentum_sign")) or conviction * 0.8),
                volume_sign=float(_opt_float(trade.get("volume_sign")) or 0.0),
                structure_sign=float(_opt_float(trade.get("structure_sign")) or 0.0),
            )
        )
    return out
