"""
Evidence-based reconciliation for order intents (Phase 1E).

Rules:
- Place-order API acceptance is NOT fill evidence.
- Empty open/history/execution lookups do NOT prove non-submission.
- Filled status requires exchange order status and/or durable execution rows.
- Duplicate exec_id cannot double-count volume (store PRIMARY KEY + in-memory dedupe).
- Out-of-order updates cannot regress terminal states.
- Reconciliation is read-only vs the exchange (no create/amend/cancel).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Protocol

from agent.intent_store import ExecutionRow, IntentStore, IntentStoreError
from agent.order_intent import (
    NEEDS_RECONCILE_STATES,
    TERMINAL_STATES,
    OrderIntent,
    OrderIntentState,
)

_MAX_PAGES = 20
_PAGE_LIMIT = 50


class ExchangeSession(Protocol):
    def get_open_orders(self, **kwargs: Any) -> dict: ...
    def get_order_history(self, **kwargs: Any) -> dict: ...
    def get_executions(self, **kwargs: Any) -> dict: ...


@dataclass(frozen=True)
class ReconcileResult:
    intent: OrderIntent
    proven: bool
    detail: str
    conflict: bool = False
    store_error: bool = False


@dataclass(frozen=True)
class _PageFetch:
    rows: list[dict]
    errors: list[str]
    complete: bool
    ret_errors: list[str]


@dataclass(frozen=True)
class _FillAggregate:
    filled_qty: str
    avg_exec_price: str
    cum_fee: str
    remaining_qty: str
    order_id: str
    exec_count: int


def _d(value: object) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _fmt(value: Decimal) -> str:
    # Exact decimal string without scientific notation / float rounding.
    return format(value, "f")


def _safe_result(response: object) -> tuple[dict | None, str | None]:
    if not isinstance(response, dict):
        return None, "malformed_response_not_dict"
    if "retCode" not in response:
        return None, "malformed_missing_retCode"
    if response.get("retCode") != 0:
        return None, f"retCode={response.get('retCode')}"
    result = response.get("result")
    if result is None:
        return {}, None
    if not isinstance(result, dict):
        return None, "malformed_result_not_dict"
    return result, None


def _list_from_result(result: dict) -> list[dict]:
    items = result.get("list")
    if items is None:
        return []
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def _paginated_fetch(
    method: Callable[..., dict],
    *,
    category: str,
    symbol: str,
    order_link_id: str,
    label: str,
) -> _PageFetch:
    rows: list[dict] = []
    errors: list[str] = []
    ret_errors: list[str] = []
    cursor: str | None = None
    complete = True

    for _ in range(_MAX_PAGES):
        kwargs: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "orderLinkId": order_link_id,
            "limit": _PAGE_LIMIT,
        }
        if cursor:
            kwargs["cursor"] = cursor
        try:
            response = method(**kwargs)
        except TimeoutError:
            errors.append(f"{label}:TimeoutError")
            complete = False
            break
        except OSError as exc:
            errors.append(f"{label}:{type(exc).__name__}")
            complete = False
            break
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}:{type(exc).__name__}")
            complete = False
            break

        result, err = _safe_result(response)
        if err is not None:
            ret_errors.append(f"{label}:{err}")
            complete = False
            break
        assert result is not None
        page = _list_from_result(result)
        rows.extend(page)
        next_cursor = str(result.get("nextPageCursor") or "").strip()
        if not next_cursor:
            break
        if next_cursor == cursor:
            # Defensive: avoid infinite loop on sticky cursor.
            complete = False
            ret_errors.append(f"{label}:sticky_cursor")
            break
        cursor = next_cursor
    else:
        complete = False
        ret_errors.append(f"{label}:max_pages")

    return _PageFetch(rows=rows, errors=errors, complete=complete, ret_errors=ret_errors)


def _match_link(rows: list[dict], client_order_id: str) -> dict | None:
    for row in rows:
        link = str(row.get("orderLinkId") or "")
        if link == client_order_id:
            return row
    return None


def _match_order_id(rows: list[dict], order_id: str) -> dict | None:
    if not order_id:
        return None
    for row in rows:
        if str(row.get("orderId") or "") == order_id:
            return row
    return None


def _executions_for_intent(
    rows: list[dict], *, client_order_id: str, order_id: str
) -> list[dict]:
    matched: list[dict] = []
    for row in rows:
        link = str(row.get("orderLinkId") or "")
        oid = str(row.get("orderId") or "")
        if link == client_order_id or (order_id and oid == order_id):
            matched.append(row)
    return matched


def _parse_execution(row: dict, *, category: str, client_order_id: str) -> ExecutionRow | None:
    exec_id = str(row.get("execId") or "").strip()
    if not exec_id:
        return None
    qty = str(row.get("execQty") or "").strip()
    price = str(row.get("execPrice") or "").strip()
    if not qty or _d(qty) is None:
        return None
    if price and _d(price) is None:
        return None
    maker = row.get("isMaker")
    is_maker: bool | None
    if isinstance(maker, bool):
        is_maker = maker
    else:
        is_maker = None
    return ExecutionRow(
        exec_id=exec_id,
        order_id=str(row.get("orderId") or ""),
        order_link_id=str(row.get("orderLinkId") or client_order_id),
        exec_qty=qty,
        exec_price=price or "0",
        exec_fee=str(row.get("execFee") or ""),
        fee_currency=str(row.get("feeCurrency") or ""),
        exec_time_ms=str(row.get("execTime") or ""),
        is_maker=is_maker,
        leaves_qty=str(row.get("leavesQty") or ""),
        category=category,
    )


def aggregate_executions(executions: list[ExecutionRow]) -> _FillAggregate:
    """Sum unique executions; qty/price/fee kept as Decimal strings (spot & linear)."""
    seen: set[str] = set()
    total_qty = Decimal("0")
    notional = Decimal("0")
    fee_total = Decimal("0")
    order_id = ""
    remaining = ""
    count = 0
    for ex in executions:
        if ex.exec_id in seen:
            continue
        seen.add(ex.exec_id)
        q = _d(ex.exec_qty)
        p = _d(ex.exec_price) or Decimal("0")
        if q is None:
            continue
        total_qty += q
        notional += q * p
        f = _d(ex.exec_fee)
        if f is not None:
            fee_total += f
        if ex.order_id and not order_id:
            order_id = ex.order_id
        if ex.leaves_qty:
            remaining = ex.leaves_qty
        count += 1
    avg = ""
    if total_qty > 0:
        avg = _fmt(notional / total_qty)
    return _FillAggregate(
        filled_qty=_fmt(total_qty) if count else "",
        avg_exec_price=avg,
        cum_fee=_fmt(fee_total) if count else "",
        remaining_qty=remaining,
        order_id=order_id,
        exec_count=count,
    )


def _state_from_exchange_row(
    row: dict,
) -> tuple[OrderIntentState | None, str, str, str]:
    """
    Map Bybit order row → intent state.

    Returns (state, order_id, cum_exec_qty, leaves_qty).
    PartiallyFilledCanceled → CANCELED with filled qty retained.
    """
    status = str(row.get("orderStatus") or "").strip()
    order_id = str(row.get("orderId") or "")
    cum = str(row.get("cumExecQty") or "")
    leaves = str(row.get("leavesQty") or "")

    if status == "Filled":
        return OrderIntentState.FILLED, order_id, cum or str(row.get("qty") or ""), "0"
    if status == "PartiallyFilled":
        return OrderIntentState.PARTIALLY_FILLED, order_id, cum, leaves
    if status == "PartiallyFilledCanceled":
        return OrderIntentState.CANCELED, order_id, cum, leaves or "0"
    if status in {"New", "Created", "Untriggered", "Triggered", "Active"}:
        return OrderIntentState.ACCEPTED, order_id, cum, leaves
    if status in {"Cancelled", "Canceled", "Deactivated"}:
        return OrderIntentState.CANCELED, order_id, cum, leaves or "0"
    if status == "Rejected":
        return OrderIntentState.REJECTED, order_id, cum or "0", leaves or "0"
    return None, order_id, cum, leaves


def _prefer_qty(order_cum: str, exec_filled: str) -> str:
    """Use the larger of order cumExecQty and summed executions when both valid."""
    a = _d(order_cum)
    b = _d(exec_filled)
    if a is None and b is None:
        return order_cum or exec_filled or ""
    if a is None:
        return exec_filled
    if b is None:
        return order_cum
    return _fmt(a if a >= b else b)


def _qty_conflict(order_qty: str, filled: str, order_cum: str, order_status: str) -> bool:
    """Detect hard inconsistencies (exec sum exceeding order qty)."""
    oq = _d(order_qty)
    filled_d = _d(filled)
    if oq is None or filled_d is None:
        return False
    if filled_d > oq:
        return True
    cum = _d(order_cum)
    if (
        order_status == "Filled"
        and cum is not None
        and filled_d > cum
        and filled_d - cum > Decimal("0")
    ):
        # Allow tiny delayed discrepancy only when equal; else conflict if exec > cum
        # after Filled — treat as conflict for fail-closed.
        return filled_d != cum and filled_d > cum
    return False


def reconcile_intent(
    session: ExchangeSession,
    store: IntentStore,
    intent: OrderIntent,
) -> ReconcileResult:
    """
    Attempt to prove exchange state via open orders, history, and executions.

    Fail-closed: ambiguous outcomes remain UNKNOWN / RECONCILIATION_REQUIRED.
    Never invents "not submitted". Never treats place-order ack as a fill.
    """
    if intent.dry_run:
        return ReconcileResult(intent, proven=True, detail="dry_run_skip")

    if intent.state in TERMINAL_STATES:
        # Still allow idempotent exec persistence if caller re-runs; no state regress.
        # Skip network for pure terminals unless evidence_status requests refresh —
        # Phase 1E: terminals are proven; return early.
        return ReconcileResult(intent, proven=True, detail=f"already_{intent.state.value}")

    if intent.state not in NEEDS_RECONCILE_STATES:
        return ReconcileResult(intent, proven=True, detail=f"skip_{intent.state.value}")

    open_fetch = _paginated_fetch(
        session.get_open_orders,
        category=intent.category,
        symbol=intent.symbol,
        order_link_id=intent.client_order_id,
        label="open_orders",
    )
    hist_fetch = _paginated_fetch(
        session.get_order_history,
        category=intent.category,
        symbol=intent.symbol,
        order_link_id=intent.client_order_id,
        label="order_history",
    )
    exec_fetch = _paginated_fetch(
        session.get_executions,
        category=intent.category,
        symbol=intent.symbol,
        order_link_id=intent.client_order_id,
        label="executions",
    )

    lookup_errors = (
        open_fetch.errors
        + hist_fetch.errors
        + exec_fetch.errors
        + open_fetch.ret_errors
        + hist_fetch.ret_errors
        + exec_fetch.ret_errors
    )
    lookups_complete = (
        open_fetch.complete and hist_fetch.complete and exec_fetch.complete
    )

    matched = _match_link(open_fetch.rows, intent.client_order_id) or _match_link(
        hist_fetch.rows, intent.client_order_id
    )
    if matched is None and intent.exchange_order_id:
        matched = _match_order_id(
            open_fetch.rows, intent.exchange_order_id
        ) or _match_order_id(hist_fetch.rows, intent.exchange_order_id)

    order_id_hint = str((matched or {}).get("orderId") or intent.exchange_order_id or "")
    raw_execs = _executions_for_intent(
        exec_fetch.rows,
        client_order_id=intent.client_order_id,
        order_id=order_id_hint,
    )
    parsed: list[ExecutionRow] = []
    for row in raw_execs:
        item = _parse_execution(
            row, category=intent.category, client_order_id=intent.client_order_id
        )
        if item is not None:
            parsed.append(item)

    # Merge previously persisted executions for aggregation (restart safety).
    try:
        prior = store.list_executions(intent.intent_id)
    except IntentStoreError as exc:
        return ReconcileResult(
            intent,
            proven=False,
            detail=f"store_unavailable:{exc}",
            store_error=True,
        )

    by_id = {e.exec_id: e for e in prior}
    for e in parsed:
        by_id[e.exec_id] = e
    all_execs = list(by_id.values())
    agg = aggregate_executions(all_execs)

    if matched is not None:
        new_state, order_id, cum, leaves = _state_from_exchange_row(matched)
        status = str(matched.get("orderStatus") or "")
        if new_state is None:
            try:
                updated, _ = store.apply_reconcile_update(
                    intent.intent_id,
                    proposed_state=OrderIntentState.UNKNOWN,
                    executions=parsed,
                    exchange_order_id=order_id or None,
                    filled_qty=_prefer_qty(cum, agg.filled_qty) or None,
                    remaining_qty=leaves or agg.remaining_qty or None,
                    avg_exec_price=agg.avg_exec_price or None,
                    cum_fee=agg.cum_fee or None,
                    evidence_status="unrecognized_order_status",
                    last_error="reconcile: matched order with unrecognized status",
                    conflict=True,
                )
            except IntentStoreError as exc:
                return ReconcileResult(
                    intent, proven=False, detail=f"store_unavailable:{exc}", store_error=True
                )
            return ReconcileResult(
                updated, proven=False, detail="unrecognized_status", conflict=True
            )

        filled = _prefer_qty(cum, agg.filled_qty)
        remaining = leaves or agg.remaining_qty
        avg = agg.avg_exec_price
        # avgPrice from order row when executions absent
        if not avg:
            avg = str(matched.get("avgPrice") or "")
        fee = agg.cum_fee or str(matched.get("cumExecFee") or "")

        if _qty_conflict(intent.qty, filled, cum, status):
            try:
                updated, _ = store.apply_reconcile_update(
                    intent.intent_id,
                    proposed_state=OrderIntentState.UNKNOWN,
                    executions=parsed,
                    exchange_order_id=order_id or None,
                    filled_qty=filled or None,
                    remaining_qty=remaining or None,
                    avg_exec_price=avg or None,
                    cum_fee=fee or None,
                    evidence_status="qty_conflict",
                    last_error="reconcile: fill quantity conflict vs order qty",
                    conflict=True,
                )
            except IntentStoreError as exc:
                return ReconcileResult(
                    intent, proven=False, detail=f"store_unavailable:{exc}", store_error=True
                )
            return ReconcileResult(
                updated, proven=False, detail="qty_conflict", conflict=True
            )

        # Rejected with zero fills
        if new_state is OrderIntentState.REJECTED and not (_d(filled) or Decimal("0")):
            filled = filled or "0"

        # Never promote to FILLED without status Filled or zero leaves + full qty evidence
        if new_state is OrderIntentState.FILLED:
            if not filled and not cum:
                # Status says Filled but no qty — inconclusive
                try:
                    updated, _ = store.apply_reconcile_update(
                        intent.intent_id,
                        proposed_state=OrderIntentState.UNKNOWN,
                        executions=parsed,
                        exchange_order_id=order_id or None,
                        evidence_status="filled_status_missing_qty",
                        last_error="reconcile: Filled status without quantity evidence",
                        conflict=True,
                    )
                except IntentStoreError as exc:
                    return ReconcileResult(
                        intent,
                        proven=False,
                        detail=f"store_unavailable:{exc}",
                        store_error=True,
                    )
                return ReconcileResult(
                    updated, proven=False, detail="filled_missing_qty", conflict=True
                )

        try:
            updated, _ = store.apply_reconcile_update(
                intent.intent_id,
                proposed_state=new_state,
                executions=parsed,
                exchange_order_id=order_id or None,
                filled_qty=filled or None,
                remaining_qty=remaining or None,
                avg_exec_price=avg or None,
                cum_fee=fee or None,
                evidence_status=f"matched_order:{status}",
                last_error="",
            )
        except IntentStoreError as exc:
            return ReconcileResult(
                intent, proven=False, detail=f"store_unavailable:{exc}", store_error=True
            )
        return ReconcileResult(
            updated, proven=True, detail=f"matched:{updated.state.value}"
        )

    # No order row — executions alone are not full order proof, but prove activity.
    if parsed or agg.exec_count:
        # Incomplete lookups → stay unresolved even with partial exec evidence.
        if not lookups_complete:
            target = OrderIntentState.UNKNOWN
            detail = "executions_with_incomplete_lookup"
            try:
                updated, _ = store.apply_reconcile_update(
                    intent.intent_id,
                    proposed_state=target,
                    executions=parsed,
                    exchange_order_id=agg.order_id or intent.exchange_order_id or None,
                    filled_qty=agg.filled_qty or None,
                    remaining_qty=agg.remaining_qty or None,
                    avg_exec_price=agg.avg_exec_price or None,
                    cum_fee=agg.cum_fee or None,
                    evidence_status=detail,
                    last_error="reconcile: executions seen but API lookup incomplete",
                )
            except IntentStoreError as exc:
                return ReconcileResult(
                    intent, proven=False, detail=f"store_unavailable:{exc}", store_error=True
                )
            return ReconcileResult(updated, proven=False, detail=detail)

        # Executions without complete order record → PARTIALLY_FILLED (not FILLED).
        proposed = OrderIntentState.PARTIALLY_FILLED
        leaves = agg.remaining_qty
        if leaves == "0" and agg.filled_qty:
            oq = _d(intent.qty)
            fq = _d(agg.filled_qty)
            if oq is not None and fq is not None and fq >= oq:
                # Strong but still without order row — keep PARTIAL (no silent FILLED).
                proposed = OrderIntentState.PARTIALLY_FILLED
        try:
            updated, _ = store.apply_reconcile_update(
                intent.intent_id,
                proposed_state=proposed,
                executions=parsed,
                exchange_order_id=agg.order_id or intent.exchange_order_id or None,
                filled_qty=agg.filled_qty or None,
                remaining_qty=agg.remaining_qty or None,
                avg_exec_price=agg.avg_exec_price or None,
                cum_fee=agg.cum_fee or None,
                evidence_status="executions_without_order_row",
                last_error="reconcile: executions found without full order row",
            )
        except IntentStoreError as exc:
            return ReconcileResult(
                intent, proven=False, detail=f"store_unavailable:{exc}", store_error=True
            )
        return ReconcileResult(updated, proven=True, detail="executions_partial")

    # No match anywhere — NOT proof of non-submission (delayed history / pagination).
    err = "reconcile inconclusive: no orderLinkId match"
    if lookup_errors:
        err += f" ({','.join(lookup_errors)})"
    if not lookups_complete:
        target = OrderIntentState.UNKNOWN
        detail = "inconclusive_incomplete_lookup"
    elif lookup_errors:
        target = OrderIntentState.UNKNOWN
        detail = "inconclusive_api_errors"
    else:
        target = OrderIntentState.RECONCILIATION_REQUIRED
        detail = "inconclusive_no_match"

    try:
        if intent.state is target:
            updated = store.transition(
                intent.intent_id,
                intent.state,
                last_error=err,
                evidence_status=detail,
            )
        else:
            try:
                updated = store.transition(
                    intent.intent_id,
                    target,
                    last_error=err,
                    evidence_status=detail,
                )
            except ValueError:
                updated = store.transition(
                    intent.intent_id,
                    OrderIntentState.UNKNOWN,
                    last_error=err,
                    evidence_status=detail,
                )
    except IntentStoreError as exc:
        return ReconcileResult(
            intent, proven=False, detail=f"store_unavailable:{exc}", store_error=True
        )
    return ReconcileResult(updated, proven=False, detail=detail)
