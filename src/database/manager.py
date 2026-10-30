"""SQLAlchemy engine and session lifecycle, configured for local SQLite."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.config import DATABASE_URL, PROJECT_ROOT

from .models import Base


class Database:
    """Lazy database manager; failures are deferred to startup/readiness."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or DATABASE_URL
        self.engine: Engine | None = None
        self.session_factory: sessionmaker[Session] | None = None
        self.initialized = False

    def initialize(self) -> None:
        """Create the engine, enforce SQLite foreign keys, and create schema."""
        if self.initialized:
            return
        url = make_url(self.database_url)
        engine_kwargs: dict[str, object] = {"pool_pre_ping": True}
        if url.get_backend_name() == "sqlite":
            database = url.database
            if database and database not in {":memory:"} and not database.startswith("file:"):
                path = Path(database)
                if not path.is_absolute():
                    path = PROJECT_ROOT / path
                path = path.resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                url = url.set(database=str(path))
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            if url.database in {None, ":memory:"}:
                engine_kwargs["poolclass"] = StaticPool

        engine = create_engine(url, **engine_kwargs)
        if url.get_backend_name() == "sqlite":
            @event.listens_for(engine, "connect")
            def _enable_sqlite_foreign_keys(connection, _record) -> None:
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

        try:
            Base.metadata.create_all(engine)
            self.engine = engine
            self.session_factory = sessionmaker(
                bind=engine,
                autoflush=False,
                expire_on_commit=False,
            )
            self.initialized = True
        except Exception:
            engine.dispose()
            raise

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a short-lived session; callers own transaction boundaries."""
        if not self.initialized or self.session_factory is None:
            raise RuntimeError("Database is not initialized")
        with self.session_factory() as session:
            yield session

    def check_connection(self) -> bool:
        """Probe the current database connection without changing any records."""
        if not self.initialized or self.engine is None:
            return False
        try:
            with self.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return True
        except SQLAlchemyError:
            return False

    def dispose(self) -> None:
        """Close pooled connections during application shutdown."""
        if self.engine is not None:
            self.engine.dispose()
        self.initialized = False
        self.engine = None
        self.session_factory = None
