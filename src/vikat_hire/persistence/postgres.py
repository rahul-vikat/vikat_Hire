from __future__ import annotations

from typing import Protocol

from psycopg_pool import ConnectionPool


class ScreeningIdRegistry(Protocol):
    """Atomic uniqueness boundary for screening execution identifiers."""

    def reserve(self, screening_id: str) -> bool:
        """Atomically claim a new screening ID; return False if already claimed."""
        ...

    def release_if_unstarted(self, screening_id: str) -> None:
        """Release a claim only when graph execution failed before checkpointing."""
        ...

    def ping(self) -> None:
        """Raise if the backing database is not ready."""
        ...


class PostgresScreeningIdRegistry:
    """Small PostgreSQL uniqueness index; LangGraph remains state authority."""

    _TABLE = "vikathire_screening_ids"

    def __init__(self, pool: ConnectionPool) -> None:
        if not isinstance(pool, ConnectionPool):
            raise TypeError("pool must be a psycopg ConnectionPool")
        self._pool = pool

    def setup(self) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self._TABLE} (
                    screening_id TEXT PRIMARY KEY,
                    reserved_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )

    def reserve(self, screening_id: str) -> bool:
        if not isinstance(screening_id, str) or not screening_id.strip():
            raise ValueError("screening_id must not be blank")
        with self._pool.connection() as connection:
            row = connection.execute(
                f"""
                INSERT INTO {self._TABLE} (screening_id)
                VALUES (%s)
                ON CONFLICT (screening_id) DO NOTHING
                RETURNING screening_id
                """,
                (screening_id,),
            ).fetchone()
        return row is not None

    def release_if_unstarted(self, screening_id: str) -> None:
        with self._pool.connection() as connection:
            connection.execute(
                f"DELETE FROM {self._TABLE} WHERE screening_id = %s",
                (screening_id,),
            )

    def ping(self) -> None:
        with self._pool.connection() as connection:
            connection.execute("SELECT 1").fetchone()
