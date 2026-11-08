"""Binding store protocol + SQLAlchemy / in-memory implementations."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.app.exchange.bindings import (
    BindingStatus,
    BindingStore,
    ExchangeAccountBinding,
    ExchangeEnvironment,
    ExchangeProvider,
)
from apps.api.app.models import ExchangeAccountBindingRow

# Re-export protocol for callers.
__all__ = [
    "BindingStore",
    "InMemoryBindingStore",
    "SqlAlchemyBindingStore",
    "binding_to_row_values",
    "row_to_binding",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def row_to_binding(row: ExchangeAccountBindingRow) -> ExchangeAccountBinding:
    return ExchangeAccountBinding(
        id=row.id,
        owner_user_id=row.owner_user_id,
        provider=ExchangeProvider(row.provider),
        environment=ExchangeEnvironment(row.environment),
        status=BindingStatus(row.status),
        display_label=row.display_label,
        credential_ref=row.credential_ref,
        telemetry_scope_id=row.telemetry_scope_id,
        enrollment_attestation=row.enrollment_attestation,
        organization_id=row.organization_id,
        enrolled_by_operator=bool(row.enrolled_by_operator),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def binding_to_row_values(binding: ExchangeAccountBinding) -> dict:
    return {
        "id": binding.id,
        "owner_user_id": binding.owner_user_id,
        "organization_id": binding.organization_id,
        "provider": binding.provider.value,
        "environment": binding.environment.value,
        "status": binding.status.value,
        "display_label": binding.display_label,
        "credential_ref": binding.credential_ref,
        "telemetry_scope_id": binding.telemetry_scope_id,
        "enrollment_attestation": binding.enrollment_attestation,
        "enrolled_by_operator": binding.enrolled_by_operator,
        "created_at": binding.created_at,
        "updated_at": binding.updated_at,
    }


class InMemoryBindingStore:
    """Offline / test repository (thread-safe for concurrent fixture tests)."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, ExchangeAccountBinding] = {}
        self._lock = threading.RLock()

    def upsert(self, binding: ExchangeAccountBinding) -> ExchangeAccountBinding:
        with self._lock:
            self._rows[binding.id] = binding
            return binding

    def get(self, binding_id: uuid.UUID) -> ExchangeAccountBinding | None:
        with self._lock:
            return self._rows.get(binding_id)

    def list_for_owner(self, owner_user_id: uuid.UUID) -> list[ExchangeAccountBinding]:
        with self._lock:
            return [b for b in self._rows.values() if b.owner_user_id == owner_user_id]

    def find_active(
        self,
        *,
        owner_user_id: uuid.UUID,
        provider: ExchangeProvider,
        environment: ExchangeEnvironment,
    ) -> ExchangeAccountBinding | None:
        with self._lock:
            for binding in self._rows.values():
                if (
                    binding.owner_user_id == owner_user_id
                    and binding.provider is provider
                    and binding.environment is environment
                    and binding.status is BindingStatus.ACTIVE
                ):
                    return binding
            return None

    def find_active_by_credential_ref(
        self, *, provider: ExchangeProvider, credential_ref: str
    ) -> ExchangeAccountBinding | None:
        with self._lock:
            for binding in self._rows.values():
                if (
                    binding.provider is provider
                    and binding.credential_ref == credential_ref
                    and binding.status is BindingStatus.ACTIVE
                ):
                    return binding
            return None

    def find_by_telemetry_scope(self, telemetry_scope_id: str) -> ExchangeAccountBinding | None:
        with self._lock:
            for binding in self._rows.values():
                if binding.telemetry_scope_id == telemetry_scope_id:
                    return binding
            return None


class SqlAlchemyBindingStore:
    """Durable repository backed by app.exchange_account_bindings."""

    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]],
    ) -> None:
        self._session_factory = session_factory

    @classmethod
    def from_sessionmaker(cls, factory: Callable[[], Session]) -> SqlAlchemyBindingStore:
        @contextmanager
        def _cm() -> Session:  # type: ignore[misc]
            session = factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return cls(_cm)

    def upsert(self, binding: ExchangeAccountBinding) -> ExchangeAccountBinding:
        with self._session_factory() as session:
            row = session.get(ExchangeAccountBindingRow, binding.id)
            values = binding_to_row_values(binding)
            values["updated_at"] = _utc_now()
            if row is None:
                session.add(ExchangeAccountBindingRow(**values))
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            session.flush()
            loaded = session.get(ExchangeAccountBindingRow, binding.id)
            assert loaded is not None
            return row_to_binding(loaded)

    def get(self, binding_id: uuid.UUID) -> ExchangeAccountBinding | None:
        with self._session_factory() as session:
            row = session.get(ExchangeAccountBindingRow, binding_id)
            return row_to_binding(row) if row else None

    def list_for_owner(self, owner_user_id: uuid.UUID) -> list[ExchangeAccountBinding]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ExchangeAccountBindingRow).where(
                    ExchangeAccountBindingRow.owner_user_id == owner_user_id
                )
            ).all()
            return [row_to_binding(r) for r in rows]

    def find_active(
        self,
        *,
        owner_user_id: uuid.UUID,
        provider: ExchangeProvider,
        environment: ExchangeEnvironment,
    ) -> ExchangeAccountBinding | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(ExchangeAccountBindingRow)
                .where(
                    ExchangeAccountBindingRow.owner_user_id == owner_user_id,
                    ExchangeAccountBindingRow.provider == provider.value,
                    ExchangeAccountBindingRow.environment == environment.value,
                    ExchangeAccountBindingRow.status == BindingStatus.ACTIVE.value,
                )
                .limit(1)
            ).first()
            return row_to_binding(row) if row else None

    def find_active_by_credential_ref(
        self, *, provider: ExchangeProvider, credential_ref: str
    ) -> ExchangeAccountBinding | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(ExchangeAccountBindingRow)
                .where(
                    ExchangeAccountBindingRow.provider == provider.value,
                    ExchangeAccountBindingRow.credential_ref == credential_ref,
                    ExchangeAccountBindingRow.status == BindingStatus.ACTIVE.value,
                )
                .limit(1)
            ).first()
            return row_to_binding(row) if row else None

    def find_by_telemetry_scope(self, telemetry_scope_id: str) -> ExchangeAccountBinding | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(ExchangeAccountBindingRow)
                .where(ExchangeAccountBindingRow.telemetry_scope_id == telemetry_scope_id)
                .limit(1)
            ).first()
            return row_to_binding(row) if row else None
