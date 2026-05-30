"""
Agent Tools MCP server — persistent memory (PostgreSQL) plus email (SMTP).

Tools:
  - register_project                            : register a project before writing memory
  - list_projects                               : list all registered projects with stats
  - put_memory, get_memory, get_memory_history  : checkpoint storage backed by Postgres
  - list_keys                                   : list all keys for a project
  - send_email                                  : Gmail SMTP (when configured)

Key naming convention  : <domain>:<entity>:<attribute>  e.g. email:last_sent
Project ID convention  : <org>:<user>:<workflow>         e.g. acme:alice:send_email
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from fastmcp import FastMCP

from src.memory import db
from src.email import sender as email_sender

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+){1,}$")
_PROJECT_RE = re.compile(r"^[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+){0,}$")


def _validate_key(v: str) -> None:
    if not _KEY_RE.match(v):
        raise ValueError(
            "key must follow <domain>:<entity> or <domain>:<entity>:<attribute> "
            "convention using alphanumeric, underscores, or hyphens. Got: " + repr(v)
        )


def _validate_project_id(v: str) -> None:
    if not _PROJECT_RE.match(v):
        raise ValueError(
            "project_id must follow <org>:<user>:<workflow> convention. Got: " + repr(v)
        )


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(server: FastMCP):
    yield
    await db.close_pool()


mcp = FastMCP(name="agent-kit", lifespan=lifespan)


@mcp.tool(
    description=(
        "Register a project before writing memory to it. "
        "Idempotent — calling again updates the name and description. "
        "project_id examples: 'acme:alice:send_email', 'acme:bob:invoice_flow'."
    )
)
async def register_project(
    project_id: str,
    name: str,
    description: str | None = None,
) -> dict:
    _validate_project_id(project_id)
    await db.register_project(project_id, name, description)
    return {"status": "ok", "project_id": project_id, "name": name}


@mcp.tool(
    description=(
        "List all registered projects with their key count and last updated time."
    )
)
async def list_projects() -> dict:
    projects = await db.list_projects()
    return {"count": len(projects), "projects": projects}


@mcp.tool(
    description=(
        "Store or update a checkpoint value in agent memory. "
        "Atomically updates the latest state and appends an immutable history entry. "
        "key examples: 'email:last_sent', 'email:retry_count', "
        "'user:123:last_login', 'workflow:step_1:status'. "
        "project_id examples: 'acme:alice:send_email', 'acme:bob:invoice_flow'."
    )
)
async def put_memory(project_id: str, key: str, value: Any) -> dict:
    _validate_project_id(project_id)
    _validate_key(key)
    try:
        await db.put_memory(project_id, key, value)
    except asyncpg.ForeignKeyViolationError:
        return {
            "status": "error",
            "message": f"Project '{project_id}' is not registered. Call register_project first.",
        }
    return {"status": "ok", "project_id": project_id, "key": key}


@mcp.tool(
    description=(
        "Retrieve the current (latest) value for a memory key. "
        "Returns the value and when it was last updated. "
        "Returns null if the key has never been set."
    )
)
async def get_memory(project_id: str, key: str) -> dict | None:
    _validate_project_id(project_id)
    _validate_key(key)
    result = await db.get_memory(project_id, key)
    if result is None:
        return {"found": False, "project_id": project_id, "key": key}
    return {"found": True, "project_id": project_id, "key": key, **result}


@mcp.tool(
    description=(
        "Retrieve the change history for a memory key, newest entries first. "
        "`limit` controls how many entries to return (1–100, default 10). "
        "Useful for auditing, debugging, or rollback decisions."
    )
)
async def get_memory_history(project_id: str, key: str, limit: int = 10) -> dict:
    _validate_project_id(project_id)
    _validate_key(key)
    if not (1 <= limit <= 100):
        raise ValueError("limit must be between 1 and 100")
    history = await db.get_memory_history(project_id, key, limit)
    return {
        "project_id": project_id,
        "key": key,
        "count": len(history),
        "entries": history,
    }


@mcp.tool(
    description=(
        "List all keys for a project. "
        "Provide either project_id or project_name — one is required."
    )
)
async def list_keys(
    project_id: str | None = None,
    project_name: str | None = None,
) -> dict:
    if not project_id and not project_name:
        return {"status": "error", "message": "Provide either project_id or project_name."}

    if not project_id:
        project_id = await db.resolve_project_by_name(project_name)
        if project_id is None:
            return {"status": "error", "message": f"No project found with name: {project_name!r}"}

    _validate_project_id(project_id)
    keys = await db.list_keys(project_id)
    return {"project_id": project_id, "count": len(keys), "keys": keys}


@mcp.tool(
    description="Send an email with both HTML and plain text versions using Gmail SMTP."
)
async def send_email(
    subject: str,
    html_body: str,
    text_body: str,
    to: list[str],
    from_name: str,
    reply_to: str | None = None,
) -> dict:
    if not email_sender.is_configured():
        return {"status": "error", "message": "Email credentials not configured on the server"}

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None,
        lambda: email_sender.send_email(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            to=to,
            from_name=from_name,
            reply_to=reply_to,
        ),
    )

    if success:
        return {"status": "ok", "message": f"Email sent successfully to {', '.join(to)}"}
    return {"status": "error", "message": "Failed to send email. Check server logs."}
