"""In-memory alert store for isolated tests. Runtime uses Postgres."""

from __future__ import annotations

from typing import Any
from uuid import UUID


class InMemoryAlertRepository:
    def __init__(self) -> None:
        self.alerts: dict[str, dict[str, Any]] = {}
        self.deliveries: dict[str, dict[str, Any]] = {}
        self.preferences: dict[str, dict[str, Any]] = {}
        self.ready = True

    def storage_kind(self) -> str:
        return "memory_test_only"

    def alerts_ready(self) -> bool:
        return self.ready

    def list_alerts(
        self,
        *,
        limit: int,
        offset: int,
        owner_user_id: UUID | None,
        severity: str | None = None,
        symbol: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = list(self.alerts.values())
        if owner_user_id is not None:
            owner = str(owner_user_id)
            rows = [r for r in rows if r.get("owner_user_id") in (None, owner)]
        if severity:
            rows = [r for r in rows if r.get("severity") == severity]
        if status:
            rows = [r for r in rows if r.get("status") == status]
        if symbol:
            sym = symbol.upper()
            rows = [r for r in rows if sym in [str(s).upper() for s in (r.get("symbols") or [])]]
        rows.sort(key=lambda r: int(r.get("created_at_ms") or 0), reverse=True)
        return rows[offset : offset + limit]

    def get_alert(self, alert_id: str, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        row = self.alerts.get(alert_id)
        if row is None:
            return None
        if owner_user_id is not None and row.get("owner_user_id") not in (None, str(owner_user_id)):
            return None
        return row

    def unread_count(self, *, owner_user_id: UUID | None) -> int:
        return sum(1 for row in self.list_alerts(limit=10_000, offset=0, owner_user_id=owner_user_id) if row.get("status") == "OPEN")

    def upsert_alerts(self, rows: list[dict[str, Any]]) -> None:
        if not self.ready:
            raise RuntimeError("alerts_schema_unavailable")
        staged = dict(self.alerts)
        for row in rows:
            key = str(row["idempotency_key"])
            if any(existing.get("idempotency_key") == key for existing in staged.values()):
                continue
            staged[str(row["alert_id"])] = dict(row)
        self.alerts = staged

    def acknowledge(self, alert_id: str, *, now_ms: int, owner_user_id: UUID | None) -> dict[str, Any] | None:
        row = self.get_alert(alert_id, owner_user_id=owner_user_id)
        if row is None:
            return None
        if row.get("status") != "ACKNOWLEDGED":
            row["status"] = "ACKNOWLEDGED"
            row["acknowledged_at_ms"] = now_ms
            row["updated_at_ms"] = now_ms
        return row

    def get_preferences(self, *, owner_user_id: UUID | None) -> dict[str, Any] | None:
        return self.preferences.get(str(owner_user_id) if owner_user_id else "operator_default")

    def save_preferences(self, prefs: dict[str, Any], *, owner_user_id: UUID | None) -> dict[str, Any]:
        key = str(owner_user_id) if owner_user_id else "operator_default"
        stored = dict(prefs)
        stored["owner_user_id"] = str(owner_user_id) if owner_user_id else None
        self.preferences[key] = stored
        return stored

    def record_delivery(self, row: dict[str, Any]) -> dict[str, Any]:
        key = str(row["idempotency_key"])
        current = self.deliveries.get(key)
        if current and current.get("status") == "confirmed":
            return current
        self.deliveries[key] = dict(row)
        return self.deliveries[key]

    def get_delivery(self, idempotency_key: str) -> dict[str, Any] | None:
        return self.deliveries.get(idempotency_key)
