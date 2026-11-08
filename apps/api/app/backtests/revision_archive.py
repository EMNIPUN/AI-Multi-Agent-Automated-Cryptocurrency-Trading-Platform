"""Postgres revision archive. Unavailable until migration 20261108_0010 is applied."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class RevisionStorageError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class PostgresRevisionArchive:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name == "sqlite":
            raise RevisionStorageError("sqlite_forbidden", "News revision archive refuses SQLite")
        self._engine = engine

    def ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM app.news_event_revisions LIMIT 1"))
            return True
        except SQLAlchemyError:
            return False

    def save_shadow(self, _payload: dict) -> None:
        if not self.ready():
            raise RevisionStorageError("storage_unavailable", "app.news_event_revisions is not available")
        raise RevisionStorageError("storage_unavailable", "shadow write requires applied migration 20261108_0010")
