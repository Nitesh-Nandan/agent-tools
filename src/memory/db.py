"""
Database layer for Agent Tools (PostgreSQL memory).

Uses asyncpg for minimal-overhead async PostgreSQL access.
All writes are transactional: UPSERT into memory_state + INSERT into memory_log.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg

from src.config import config


# ---------------------------------------------------------------------------
# Pool singleton
# ---------------------------------------------------------------------------

_pool: asyncpg.Pool | None = None


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
        format="text",
    )


async def get_pool() -> asyncpg.Pool:
    """Return (and lazily create) the shared connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=config.db_url,
            init=_init_conn,
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
# SQL
# ---------------------------------------------------------------------------

_UPSERT_PROJECT = """
INSERT INTO projects (project_id, name, description)
VALUES ($1, $2, $3)
ON CONFLICT (project_id)
DO UPDATE SET
    name        = EXCLUDED.name,
    description = EXCLUDED.description;
"""

_LIST_PROJECTS = """
SELECT
    p.project_id,
    p.name,
    p.description,
    p.created_at,
    COUNT(ms.key)      AS key_count,
    MAX(ms.updated_at) AS last_updated
FROM projects p
LEFT JOIN memory_state ms ON ms.project_id = p.project_id
GROUP BY p.project_id, p.name, p.description, p.created_at
ORDER BY p.created_at DESC;
"""

_UPSERT_STATE = """
INSERT INTO memory_state (project_id, key, value, updated_at)
VALUES ($1, $2, $3, now())
ON CONFLICT (project_id, key)
DO UPDATE SET
    value      = EXCLUDED.value,
    updated_at = now();
"""

_INSERT_LOG = """
INSERT INTO memory_log (project_id, key, value, created_at)
VALUES ($1, $2, $3, now());
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

_RESOLVE_PROJECT_BY_NAME = """
SELECT project_id FROM projects WHERE name = $1 LIMIT 1;
"""

_LIST_KEYS = """
SELECT key, value, updated_at
FROM memory_state
WHERE project_id = $1
ORDER BY key;
"""


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

async def register_project(
    project_id: str,
    name: str,
    description: str | None = None,
) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_UPSERT_PROJECT, project_id, name, description)


async def list_projects() -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_PROJECTS)
    return [
        {
            "project_id": row["project_id"],
            "name": row["name"],
            "description": row["description"],
            "created_at": row["created_at"].isoformat(),
            "key_count": row["key_count"],
            "last_updated": row["last_updated"].isoformat() if row["last_updated"] else None,
        }
        for row in rows
    ]


async def put_memory(project_id: str, key: str, value: Any) -> None:
    """Atomically upsert latest state and append an immutable log entry."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_UPSERT_STATE, project_id, key, value)
            await conn.execute(_INSERT_LOG, project_id, key, value)


async def get_memory(project_id: str, key: str) -> dict | None:
    """Return the latest snapshot for a key, or None if not found."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_STATE, project_id, key)
    if row is None:
        return None
    return {
        "value": row["value"],
        "updated_at": row["updated_at"].isoformat(),
    }


async def get_memory_history(project_id: str, key: str, limit: int = 10) -> list[dict]:
    """Return the most recent `limit` log entries for a key, newest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_GET_HISTORY, project_id, key, limit)
    return [
        {"value": row["value"], "created_at": row["created_at"].isoformat()}
        for row in rows
    ]


async def resolve_project_by_name(name: str) -> str | None:
    """Return the project_id for a given project name, or None if not found."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(_RESOLVE_PROJECT_BY_NAME, name)


async def list_keys(project_id: str) -> list[dict]:
    """Return all current keys for a project."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_KEYS, project_id)
    return [
        {"key": row["key"], "updated_at": row["updated_at"].isoformat()}
        for row in rows
    ]
