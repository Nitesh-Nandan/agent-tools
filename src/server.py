"""
Agent Tools MCP server — persistent memory (PostgreSQL) plus email (SMTP).

Tools:
  - put_memory, get_memory, get_memory_history : agent memory backed by Postgres
  - send_email                                 : Gmail SMTP (when configured)

Key naming convention  : <domain>:<entity>:<attribute>  e.g. email:last_sent
Project ID convention  : <org>:<user>:<workflow>         e.g. acme:alice:send_email
"""

from __future__ import annotations

import asyncio
import re
from contextlib import asynccontextmanager
from typing import Any

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
        "Store or update a value in agent memory. "
        "Atomically updates the latest state and appends an immutable history entry. "
        "key examples: 'email:last_sent', 'email:retry_count', "
        "'user:123:last_login', 'workflow:step_1:status'. "
        "project_id examples: 'acme:alice:send_email', 'acme:bob:invoice_flow'."
    )
)
async def put_memory(project_id: str, key: str, value: Any) -> dict:
    """Upsert memory_state and append to memory_log in a single transaction."""
    _validate_project_id(project_id)
    _validate_key(key)
    await db.put_memory(project_id, key, value)
    return {"status": "ok", "project_id": project_id, "key": key}


@mcp.tool(
    description=(
        "Retrieve the current (latest) value for a memory key. "
        "Returns the value and when it was last updated. "
        "Returns null if the key has never been set."
    )
)
async def get_memory(project_id: str, key: str) -> dict | None:
    """Fetch latest value from memory_state."""
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
    """Fetch ordered history from memory_log."""
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
        "Send an email with both HTML and plain text versions using Gmail SMTP."
    )
)
async def send_email(
    subject: str,
    html_body: str,
    text_body: str,
    to: list[str],
    reply_to: str | None = None,
    from_name: str | None = None,
) -> dict:
    """Send an email using configured SMTP credentials."""
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
            reply_to=reply_to,
            from_name=from_name,
        ),
    )

    if success:
        return {"status": "ok", "message": f"Email sent successfully to {', '.join(to)}"}
    return {"status": "error", "message": "Failed to send email. Check server logs."}
