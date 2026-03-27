"""
Database layer for Agent Tools (PostgreSQL memory).

Uses asyncpg for minimal-overhead async PostgreSQL access.
All writes are transactional: UPSERT into memory_state + INSERT into memory_log.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

import asyncpg

from src.config import config


# ---------------------------------------------------------------------------
# Pool singleton
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Return (and lazily create) the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=config.db_host,
            port=config.db_port,
            database=config.db_name,
            user=config.db_user,
            password=config.db_password,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    """Gracefully close the pool on shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

_UPSERT_STATE = """
INSERT INTO memory_state (project_id, key, value, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (project_id, key)
DO UPDATE SET
    value      = EXCLUDED.value,
    updated_at = now();
"""

_INSERT_LOG = """
INSERT INTO memory_log (id, project_id, key, value, created_at)
VALUES ($1, $2, $3, $4, now());
"""

_GET_STATE = """
SELECT value, updated_at
FROM memory_state
WHERE project_id = $1 AND key = $2;
"""

_GET_HISTORY = """
SELECT value, created_at
FROM memory_log
WHERE project_id = $1 AND key = $2
ORDER BY created_at DESC
LIMIT $3;
"""


async def put_memory(
    project_id: str,
    key: str,
    value: Any,
) -> None:
    """
    Atomically upsert latest state and append an immutable log entry.

    Both writes happen inside a single transaction — either both succeed
    or both are rolled back.
    """
    import json

    pool = await get_pool()
    value_json = json.dumps(value)
    log_id = str(uuid.uuid4())

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_UPSERT_STATE, project_id, key, value_json)
            await conn.execute(_INSERT_LOG, log_id, project_id, key, value_json)


async def get_memory(
    project_id: str,
    key: str,
) -> dict | None:
    """
    Return the latest snapshot for a key, or None if not found.

    Returns: {"value": ..., "updated_at": "2026-..."}
    """
    import json

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_STATE, project_id, key)

    if row is None:
        return None

    return {
        "value": json.loads(row["value"]),
        "updated_at": row["updated_at"].isoformat(),
    }


async def get_memory_history(
    project_id: str,
    key: str,
    limit: int = 10,
) -> list[dict]:
    """
    Return the most recent `limit` log entries for a key, newest first.

    Returns: [{"value": ..., "created_at": "2026-..."}, ...]
    """
    import json

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_GET_HISTORY, project_id, key, limit)

    return [
        {
            "value": json.loads(row["value"]),
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]
