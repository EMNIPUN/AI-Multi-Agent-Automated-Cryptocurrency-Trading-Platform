"""Futures order information gathering for Orchestrator chat.

Before a MAINNET open proposal is created, chat collects:
symbol, side, order type (Market/Limit), limit price (if Limit),
qty, leverage, optional SL/TP.

Approve is still required after the proposal is ready.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from agent.orchestrator.agent_registry import normalize_symbol


_LOCK = threading.Lock()
_SESSION: "FuturesIntakeSession | None" = None
_TTL_MS = 20 * 60_000

REQUIRED_FIELDS = ("side", "order_type", "qty", "leverage")
OPTIONAL_FIELDS = ("stop_loss", "take_profit")


@dataclass
class FuturesIntakeSession:
    symbol: str
    category: str = "linear"
    side: str | None = None  # BUY | SELL
    order_type: str | None = None  # Market | Limit
    limit_price: float | None = None
    qty: str | None = None
    leverage: int | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    skip_sl: bool = False
    skip_tp: bool = False
    # Trade margin in USDT (not account balance). Sized into qty with leverage × price.
    margin_usdt: float | None = None
    account_usdt: float | None = None
    qty_from_margin: bool = False
    created_ms: int = 0
    expires_ms: int = 0
    notes: list[str] = field(default_factory=list)

    def missing(self) -> list[str]:
        missing: list[str] = []
        if not self.side:
            missing.append("side")
        if not self.order_type:
            missing.append("order_type")
        if self.order_type == "Limit" and self.limit_price is None:
            missing.append("limit_price")
        if not self.qty and self.margin_usdt is None:
            missing.append("margin_or_qty")
        if self.leverage is None:
            missing.append("leverage")
        if not self.skip_sl and self.stop_loss is None:
            missing.append("stop_loss_or_skip")
        if not self.skip_tp and self.take_profit is None:
            missing.append("take_profit_or_skip")
        return missing

    def is_complete(self) -> bool:
        return len(self.missing()) == 0

    def to_public(self) -> dict[str, Any]:
        body = asdict(self)
        body["missing"] = self.missing()
        body["complete"] = self.is_complete()
        return body


def reset_futures_intake_for_tests() -> None:
    global _SESSION
    with _LOCK:
        _SESSION = None


def get_active_intake() -> FuturesIntakeSession | None:
    global _SESSION
    with _LOCK:
        now = int(time.time() * 1000)
        if _SESSION is None:
            return None
        if now >= _SESSION.expires_ms:
            _SESSION = None
            return None
        return _SESSION


def clear_intake() -> None:
    global _SESSION
    with _LOCK:
        _SESSION = None


def _filled_summary(session: FuturesIntakeSession) -> list[str]:
    filled: list[str] = []
    if session.side:
        filled.append(f"Side {session.side}")
    if session.order_type:
        filled.append(session.order_type)
    if session.limit_price is not None:
        filled.append(f"price {session.limit_price}")
    if session.margin_usdt is not None:
        filled.append(f"trade size {session.margin_usdt} USDT")
    if session.qty:
        filled.append(f"qty {session.qty}")
    if session.account_usdt is not None:
        filled.append(f"account ~{session.account_usdt} USDT")
    if session.leverage is not None:
        filled.append(f"{session.leverage}x")
    if session.stop_loss is not None:
        filled.append(f"SL {session.stop_loss}")
    elif session.skip_sl:
        filled.append("SL skipped")
    if session.take_profit is not None:
        filled.append(f"TP {session.take_profit}")
    elif session.skip_tp:
        filled.append("TP skipped")
    return filled


def _prompt_for(missing: list[str], session: FuturesIntakeSession) -> str:
    account_hint = ""
    if session.account_usdt is not None:
        account_hint = f" (your account ≈ {session.account_usdt} USDT — don’t use it all)"
    labels = {
        "side": 'Side — "Buy/Long" or "Sell/Short"',
        "order_type": 'Order type — "Market" or "Limit"',
        "limit_price": "Limit price (example: 74.50)",
        "margin_or_qty": (
            f'How many USDT to use for this trade{account_hint}? '
            'e.g. "use 3 USDT" or contract qty like "qty 0.07"'
        ),
        "qty": "Contract quantity — e.g. qty 0.07",
        "leverage": "Leverage — e.g. leverage 5x (1–50)",
        "stop_loss_or_skip": 'Stop loss — e.g. sl 73.0 (or "skip sl")',
        "take_profit_or_skip": 'Take profit — e.g. tp 76.0 (or "skip tp")',
    }
    lines = [
        f"Let's finish your live {session.symbol} futures order.",
        "",
    ]
    filled = _filled_summary(session)
    if filled:
        lines.append("Already set: " + ", ".join(filled) + ".")
        lines.append("")
    lines.append("Still need:")
    for key in missing:
        lines.append(f"• {labels.get(key, key)}")
    lines.append("")
    lines.append(
        'Reply in one message, e.g. "Market leverage 5 use 3 USDT" '
        'or "Buy Market qty 0.07 leverage 5 skip sl skip tp".'
    )
    lines.append(
        'Limit example: "Sell Limit price 74.5 qty 0.07 leverage 3 sl 75.2 tp 73.0".'
    )
    lines.append("Nothing is sent to Bybit until you reply Approve live trade.")
    return "\n".join(lines)


def _normalize_intake_symbol(symbol: str) -> str:
    try:
        return normalize_symbol(symbol)
    except Exception:  # noqa: BLE001
        sym = str(symbol or "HYPEUSDT").upper()
        if not sym.endswith("USDT") and len(sym) <= 10:
            sym = f"{sym}USDT"
        return sym


def _explicit_symbol_in_message(text: str) -> str | None:
    lower = (text or "").lower()
    for tok, sym in (
        ("hype", "HYPEUSDT"),
        ("btc", "BTCUSDT"),
        ("eth", "ETHUSDT"),
        ("sol", "SOLUSDT"),
        ("bnb", "BNBUSDT"),
    ):
        if tok in lower:
            return sym
    return None


def start_futures_intake(
    *,
    symbol: str = "HYPEUSDT",
    category: str = "linear",
    message: str = "",
) -> dict[str, Any]:
    """Start futures intake; reuse an active session instead of wiping collected fields."""
    from apps.api.app.exchange.bybit_live_adapter import live_mutate_allowed

    sym = _normalize_intake_symbol(symbol)
    explicit = _explicit_symbol_in_message(message)
    if explicit:
        sym = explicit

    existing = get_active_intake()
    # "Place order" mid-checklist must continue — never wipe qty/side already collected.
    if existing is not None and (explicit is None or existing.symbol == sym):
        return continue_futures_intake(message)

    global _SESSION
    now = int(time.time() * 1000)
    session = FuturesIntakeSession(
        symbol=sym,
        category=category or "linear",
        created_ms=now,
        expires_ms=now + _TTL_MS,
    )
    seeded_from_analysis = _seed_from_last_analysis(session)
    with _LOCK:
        _SESSION = session

    if message:
        _apply_parsed(session, message)

    if session.is_complete():
        return _finalize_intake(session)

    missing = session.missing()
    summary = _prompt_for(missing, session)
    if seeded_from_analysis:
        seed_bits = []
        if session.side:
            seed_bits.append(f"side {session.side}")
        if session.stop_loss is not None:
            seed_bits.append(f"SL {session.stop_loss}")
        if session.take_profit is not None:
            seed_bits.append(f"TP {session.take_profit}")
        seed_txt = ", ".join(seed_bits) if seed_bits else "available levels"
        summary = (
            f"Using your latest {session.symbol} analysis ({seed_txt}). "
            "Reply Buy or Sell to override the side.\n\n"
            + summary
        )
    return {
        "ok": True,
        "intake": True,
        "awaiting_intake": True,
        "symbol": session.symbol,
        "category": session.category,
        "missing": missing,
        "collected": session.to_public(),
        "seeded_from_analysis": seeded_from_analysis,
        "live_orders": True,
        "exchange_order_sent": False,
        "awaiting_human_approval": False,
        "execution_mode": "LIVE",
        "preferred_mode": "LIVE",
        "gates_armed": live_mutate_allowed(),
        "summary": summary,
    }


def _is_place_or_approve_nudge(text: str) -> bool:
    lower = (text or "").lower().strip().rstrip(".")
    if not lower:
        return False
    if re.fullmatch(
        r"(?:ok(?:ay)?|please|yes)?\s*"
        r"(?:place(?:\s+the)?\s+order|place\s+it|go\s+ahead|use\s+that|"
        r"approve(?:\s+live(?:\s+trade)?)?|confirm(?:\s+live(?:\s+trade)?)?)"
        r"(?:\s+please)?",
        lower,
    ):
        return True
    return lower in {
        "ok",
        "okay",
        "yes",
        "place order",
        "place the order",
        "approve",
        "approve live trade",
        "use entry",
        "use analysis",
        "use analysis entry",
        "use entry price",
    }


def continue_futures_intake(message: str) -> dict[str, Any]:
    """Apply user answers into the active intake; finalize when complete."""
    session = get_active_intake()
    if session is None:
        return start_futures_intake(symbol="HYPEUSDT", message=message)

    raw = (message or "").strip()
    nudge = _is_place_or_approve_nudge(raw)
    if raw and not nudge:
        _apply_parsed(session, raw)
    else:
        # Limit with no price yet → reuse analysis entry / last price so Approve can proceed.
        _maybe_seed_limit_price(session)
        _maybe_size_from_margin(session)

    if session.is_complete():
        return _finalize_intake(session)

    # Still incomplete after a place/approve nudge — try seeding once more, then guide.
    if nudge:
        _maybe_seed_limit_price(session)
        if session.is_complete():
            return _finalize_intake(session)

    missing = session.missing()
    summary = _prompt_for(missing, session)
    if nudge:
        summary = (
            "Almost ready — I still need the item(s) below before I can create the "
            "Approve proposal (nothing is sent to Bybit yet).\n\n"
            + summary
        )
    suggested = None
    if "limit_price" in missing:
        suggested = _price_hint(session)
        if suggested is not None:
            summary += (
                f"\n\nSuggested limit from your analysis: {suggested}. "
                f'Reply "use entry" or "limit price {suggested}", or switch to Market.'
            )
    return {
        "ok": True,
        "intake": True,
        "awaiting_intake": True,
        "symbol": session.symbol,
        "category": session.category,
        "missing": missing,
        "collected": session.to_public(),
        "suggested_limit_price": suggested,
        "live_orders": True,
        "exchange_order_sent": False,
        "awaiting_human_approval": False,
        "execution_mode": "LIVE",
        "preferred_mode": "LIVE",
        "summary": summary,
    }


def _seed_from_last_analysis(session: FuturesIntakeSession) -> bool:
    """Pre-fill side / SL / TP from the latest matching analysis when present."""
    try:
        from agent.orchestrator.analysis_memory import latest_analysis
    except Exception:  # noqa: BLE001
        return False
    snap = latest_analysis(symbol=session.symbol)
    if not snap:
        return False
    used = False
    side = str(snap.get("side") or "").upper()
    if side in {"BUY", "SELL"} and session.side is None:
        session.side = side
        used = True
    sl = snap.get("stop_loss")
    if sl is not None and session.stop_loss is None and not session.skip_sl:
        try:
            session.stop_loss = float(sl)
            used = True
        except (TypeError, ValueError):
            pass
    tp = snap.get("take_profit")
    if tp is not None and session.take_profit is None and not session.skip_tp:
        try:
            session.take_profit = float(tp)
            used = True
        except (TypeError, ValueError):
            pass
    return used


def _price_hint(session: FuturesIntakeSession) -> float | None:
    """Best available mark/last for sizing qty from USDT margin."""
    if session.limit_price is not None and session.limit_price > 0:
        return float(session.limit_price)
    try:
        from agent.orchestrator.analysis_memory import latest_analysis

        snap = latest_analysis(symbol=session.symbol)
    except Exception:  # noqa: BLE001
        snap = None
    if isinstance(snap, dict):
        # Prefer analysis entry for Limit orders; last_price as fallback.
        for key in ("entry", "last_price"):
            raw = snap.get(key)
            try:
                value = float(raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
            if value > 0:
                return value
    return None


def _maybe_seed_limit_price(session: FuturesIntakeSession) -> bool:
    """When Limit is chosen without a price, reuse analysis entry / last price."""
    if session.order_type != "Limit" or session.limit_price is not None:
        return False
    hint = _price_hint(session)
    if hint is None or hint <= 0:
        return False
    session.limit_price = float(hint)
    session.notes.append(f"limit price {hint} from analysis entry/last")
    return True


def _maybe_size_from_margin(session: FuturesIntakeSession) -> None:
    """Derive contract qty from trade-margin USDT × leverage / price, rounded to lot size."""
    if session.margin_usdt is None:
        return
    # Explicit contract qty wins unless we are still margin-driven.
    if session.qty and not session.qty_from_margin:
        return
    price = _price_hint(session)
    if price is None or price <= 0:
        return
    from agent.orchestrator.symbol_rules import normalize_qty

    lev = int(session.leverage or 1)
    raw = (float(session.margin_usdt) * lev) / price
    if raw <= 0:
        return
    rounded = normalize_qty(session.symbol, raw, price=price)
    if not rounded:
        return
    session.qty = rounded
    session.qty_from_margin = True
    session.notes.append(
        f"qty {session.qty} from trade size {session.margin_usdt} USDT × {lev}x @ {price}"
    )


def _apply_parsed(session: FuturesIntakeSession, text: str) -> None:
    raw = text or ""
    lower = raw.lower()

    # Side
    if re.search(r"\b(buy|long)\b", lower):
        session.side = "BUY"
    elif re.search(r"\b(sell|short)\b", lower):
        session.side = "SELL"

    # Order type
    if re.search(r"\bmarket\b", lower):
        session.order_type = "Market"
        session.limit_price = None
    elif re.search(r"\blimit\b", lower):
        session.order_type = "Limit"

    # Leverage
    lev = re.search(r"\b(?:leverage|lev|x)\s*[:=]?\s*(\d{1,2})\s*x?\b", lower)
    if not lev:
        lev = re.search(r"\b(\d{1,2})\s*x\b", lower)
    if lev:
        value = int(lev.group(1))
        if 1 <= value <= 50:
            session.leverage = value

    # Explicit contract qty
    qty = re.search(r"\b(?:qty|quantity|size|amount)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b", lower)
    if qty:
        session.qty = qty.group(1)
        session.margin_usdt = None
        session.qty_from_margin = False

    # Account balance vs trade size (USDT).
    # "have/account/balance 5 USDT" → account hint only (ask how much to use).
    # "use/risk/margin 3 USDT" or "3 USDT for trade" → trade margin.
    trade_usdt = re.search(
        r"\b(?:use|risk|margin|spend|allocate)\s+([0-9]+(?:\.[0-9]+)?)\s*usdt\b",
        lower,
    )
    if not trade_usdt:
        trade_usdt = re.search(
            r"\b([0-9]+(?:\.[0-9]+)?)\s*usdt\s+(?:for\s+)?(?:this\s+)?(?:trade|order|margin)\b",
            lower,
        )
    account_usdt = re.search(
        r"\b(?:account|balance|wallet|have)\b(?:\D{0,48}?)([0-9]+(?:\.[0-9]+)?)\s*usdt\b",
        lower,
    )
    if trade_usdt:
        try:
            session.margin_usdt = float(trade_usdt.group(1))
            session.qty_from_margin = True
            session.qty = None
        except (TypeError, ValueError):
            pass
    elif account_usdt:
        try:
            session.account_usdt = float(account_usdt.group(1))
        except (TypeError, ValueError):
            pass
    else:
        bare_usdt = re.search(r"\b([0-9]+(?:\.[0-9]+)?)\s*usdt\b", lower)
        if bare_usdt and session.qty is None:
            try:
                session.margin_usdt = float(bare_usdt.group(1))
                session.qty_from_margin = True
                session.qty = None
            except (TypeError, ValueError):
                pass

    # Limit / entry price (explicit number)
    price = re.search(
        r"\b(?:limit(?:\s*price)?|price|entry)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b",
        lower,
    )
    if price and session.order_type == "Limit":
        session.limit_price = float(price.group(1))
    elif price and "limit" in lower:
        session.order_type = "Limit"
        session.limit_price = float(price.group(1))

    # "use entry" / "use analysis price" → analysis entry as limit
    if session.order_type == "Limit" and session.limit_price is None:
        if re.search(r"\b(use\s+entry|use\s+analysis|analysis\s+entry|entry\s+price)\b", lower):
            _maybe_seed_limit_price(session)

    # SL / TP or skip
    if re.search(r"\b(skip\s*sl|no\s*sl|without\s*sl)\b", lower):
        session.skip_sl = True
        session.stop_loss = None
    else:
        sl = re.search(r"\b(?:sl|stop(?:\s*loss)?)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b", lower)
        if sl:
            session.stop_loss = float(sl.group(1))
            session.skip_sl = False

    if re.search(r"\b(skip\s*tp|no\s*tp|without\s*tp)\b", lower):
        session.skip_tp = True
        session.take_profit = None
    else:
        tp = re.search(r"\b(?:tp|take(?:\s*profit)?)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\b", lower)
        if tp:
            session.take_profit = float(tp.group(1))
            session.skip_tp = False

    # Bare number while a single numeric field is missing (limit / trade USDT / leverage).
    bare = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*", lower)
    if bare:
        if session.order_type == "Limit" and session.limit_price is None:
            session.limit_price = float(bare.group(1))
        elif session.margin_usdt is None and session.qty is None:
            # When we still need trade size, a bare number means USDT margin (e.g. "3").
            try:
                session.margin_usdt = float(bare.group(1))
                session.qty_from_margin = True
            except (TypeError, ValueError):
                session.qty = bare.group(1)
                session.qty_from_margin = False
        elif session.leverage is None:
            try:
                value = int(float(bare.group(1)))
            except (TypeError, ValueError):
                value = 0
            if 1 <= value <= 50:
                session.leverage = value

    # Symbol override if present
    explicit = _explicit_symbol_in_message(lower)
    if explicit:
        session.symbol = explicit

    # Choosing Limit without a number → seed from analysis so the checklist can finish.
    if session.order_type == "Limit" and session.limit_price is None:
        _maybe_seed_limit_price(session)

    # Leverage changed after margin sizing → rebuild qty.
    if session.margin_usdt is not None and session.leverage is not None:
        session.qty_from_margin = True
    _maybe_size_from_margin(session)


def _finalize_intake(session: FuturesIntakeSession) -> dict[str, Any]:
    """Convert a complete intake into a pending live proposal (Approve required)."""
    from agent.orchestrator.live_trade_proposals import create_manual_live_proposal
    from agent.orchestrator.symbol_rules import (
        fetch_instrument_public,
        normalize_price,
        normalize_qty,
    )

    _maybe_size_from_margin(session)
    if not session.qty:
        missing = session.missing()
        if "margin_or_qty" not in missing:
            missing.append("margin_or_qty")
        return {
            "ok": False,
            "intake": True,
            "awaiting_intake": True,
            "missing": missing,
            "collected": session.to_public(),
            "summary": _prompt_for(missing, session),
            "live_orders": True,
            "exchange_order_sent": False,
            "awaiting_human_approval": False,
            "execution_mode": "LIVE",
        }

    instrument = fetch_instrument_public(session.symbol, session.category)
    price_hint = _price_hint(session)
    qty = normalize_qty(session.symbol, session.qty, price=price_hint, instrument=instrument)
    if not qty:
        return {
            "ok": False,
            "intake": True,
            "awaiting_intake": True,
            "missing": ["margin_or_qty"],
            "collected": session.to_public(),
            "summary": (
                f"Could not size a valid {session.symbol} qty from that USDT amount "
                "(Bybit min notional / lot size). Try a slightly larger trade size, "
                'e.g. "use 3 USDT" or "qty 0.07".\n\n'
                + _prompt_for(["margin_or_qty"], session)
            ),
            "live_orders": True,
            "exchange_order_sent": False,
            "execution_mode": "LIVE",
        }
    session.qty = qty

    limit_price = session.limit_price
    if limit_price is not None:
        normalized_limit = normalize_price(session.symbol, limit_price, instrument=instrument)
        if normalized_limit is not None:
            limit_price = float(normalized_limit)

    stop_loss = session.stop_loss
    if stop_loss is not None:
        normalized_sl = normalize_price(session.symbol, stop_loss, instrument=instrument)
        if normalized_sl is not None:
            stop_loss = float(normalized_sl)

    take_profit = session.take_profit
    if take_profit is not None:
        normalized_tp = normalize_price(session.symbol, take_profit, instrument=instrument)
        if normalized_tp is not None:
            take_profit = float(normalized_tp)

    body = create_manual_live_proposal(
        symbol=session.symbol,
        category=session.category,
        side=str(session.side),
        order_type=str(session.order_type or "Market"),
        qty=str(session.qty),
        leverage=int(session.leverage or 1),
        limit_price=limit_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )
    # Keep checklist if proposal was not created (gates off / invalid) so Approve isn't orphaned.
    if isinstance(body, dict) and body.get("ok") and body.get("proposal_id"):
        clear_intake()
    elif isinstance(body, dict):
        missing = session.missing()
        gate_note = str(body.get("summary") or "Could not create a live proposal yet.")
        body = {
            **body,
            "intake": True,
            "awaiting_intake": True,
            "missing": missing,
            "collected": session.to_public(),
            "summary": gate_note + "\n\n" + _prompt_for(missing, session),
        }
    return body


def looks_like_intake_answer(message: str) -> bool:
    """True when the message likely fills order fields for an active intake."""
    text = (message or "").lower().strip()
    if not text:
        return False
    # Analysis / clarification requests are not order-field answers.
    if any(
        phrase in text
        for phrase in (
            "analysis",
            "analyse",
            "analyze",
            "full report",
            "give me plan",
            "give my plan",
            "trading plan",
            "before decide",
            "firstly",
            "clarify",
            "what do you mean",
        )
    ):
        return False
    cues = (
        "buy",
        "sell",
        "long",
        "short",
        "market",
        "limit",
        "leverage",
        "lev",
        "qty",
        "quantity",
        "skip sl",
        "skip tp",
        "stop loss",
        "take profit",
        " price",
        "entry",
        "usdt",
    )
    if any(c in text for c in cues):
        return True
    if re.search(r"\b\d{1,2}\s*x\b", text):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\b", text) and get_active_intake() is not None:
        return True
    return False


def is_place_order_confirm(message: str) -> bool:
    """True for short place-order phrases that should continue intake, not restart it."""
    text = (message or "").lower().strip()
    if not text:
        return False
    return bool(
        re.fullmatch(
            r"(?:please\s+)?(?:place(?:\s+the)?\s+order|place\s+it|go\s+ahead|"
            r"place(?:\s+the)?\s+trade|use\s+that)(?:\s+please)?\.?",
            text,
        )
    )
