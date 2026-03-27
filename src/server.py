"""
Agent Tools MCP server — persistent memory (PostgreSQL) plus email (SMTP).

Tools:
  - put_memory, get_memory, get_memory_history : agent memory backed by Postgres
  - send_email                                 : Gmail SMTP (when configured)

Key naming convention  : <domain>:<entity>:<attribute>  e.g. email:last_sent
Project ID convention  : <org>:<user>:<workflow>         e.g. acme:alice:send_email
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field, field_validator

from src.memory import db

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_KEY_RE = re.compile(r"^[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+){1,}$")
_PROJECT_RE = re.compile(r"^[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+){0,}$")


def _validate_key(v: str) -> str:
    if not _KEY_RE.match(v):
        raise ValueError(
            "key must follow <domain>:<entity> or <domain>:<entity>:<attribute> "
            "convention using alphanumeric, underscores, or hyphens. Got: " + repr(v)
        )
    return v


def _validate_project_id(v: str) -> str:
    if not _PROJECT_RE.match(v):
        raise ValueError(
            "project_id must follow <org>:<user>:<workflow> convention. Got: " + repr(v)
        )
    return v


# ---------------------------------------------------------------------------
# Pydantic input models
# ---------------------------------------------------------------------------


class PutMemoryInput(BaseModel):
    project_id: Annotated[str, Field(description="<org>:<user>:<workflow>")]
    key: Annotated[str, Field(description="<domain>:<entity>:<attribute>")]
    value: Annotated[Any, Field(description="Any JSON-serialisable value")]

    @field_validator("key")
    @classmethod
    def check_key(cls, v: str) -> str:
        return _validate_key(v)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return _validate_project_id(v)


class GetMemoryInput(BaseModel):
    project_id: Annotated[str, Field(description="<org>:<user>:<workflow>")]
    key: Annotated[str, Field(description="<domain>:<entity>:<attribute>")]

    @field_validator("key")
    @classmethod
    def check_key(cls, v: str) -> str:
        return _validate_key(v)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return _validate_project_id(v)


class GetMemoryHistoryInput(BaseModel):
    project_id: Annotated[str, Field(description="<org>:<user>:<workflow>")]
    key: Annotated[str, Field(description="<domain>:<entity>:<attribute>")]
    limit: Annotated[int, Field(default=10, ge=1, le=100, description="Max entries to return")]

    @field_validator("key")
    @classmethod
    def check_key(cls, v: str) -> str:
        return _validate_key(v)

    @field_validator("project_id")
    @classmethod
    def check_project_id(cls, v: str) -> str:
        return _validate_project_id(v)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(name="agent-tools")


@mcp.tool(
    description=(
        "Store or update a value in agent memory. "
        "Atomically updates the latest state and appends an immutable history entry. "
        # key examples make it obvious what the colon-separated format means
        "key examples: 'email:last_sent', 'email:retry_count', 'user:123:last_login', 'workflow:step_1:status'. "
        # project_id scopes memory to a workflow so different agents don't collide
        "project_id examples: 'acme:alice:send_email', 'acme:bob:invoice_flow'."
    )
)
async def put_memory(
    project_id: str,
    key: str,
    value: Any,
) -> dict:
    """Upsert memory_state and append to memory_log in a single transaction."""
    inp = PutMemoryInput(project_id=project_id, key=key, value=value)
    await db.put_memory(inp.project_id, inp.key, inp.value)
    return {"status": "ok", "project_id": inp.project_id, "key": inp.key}


@mcp.tool(
    description=(
        "Retrieve the current (latest) value for a memory key. "
        "Returns the value and when it was last updated. "
        "Returns null if the key has never been set."
    )
)
async def get_memory(
    project_id: str,
    key: str,
) -> dict | None:
    """Fetch latest value from memory_state."""
    inp = GetMemoryInput(project_id=project_id, key=key)
    result = await db.get_memory(inp.project_id, inp.key)
    if result is None:
        return {"found": False, "project_id": inp.project_id, "key": inp.key}
    return {"found": True, "project_id": inp.project_id, "key": inp.key, **result}


@mcp.tool(
    description=(
        "Retrieve the change history for a memory key, newest entries first. "
        "`limit` controls how many entries to return (1–100, default 10). "
        "Useful for auditing, debugging, or rollback decisions."
    )
)
async def get_memory_history(
    project_id: str,
    key: str,
    limit: int = 10,
) -> dict:
    """Fetch ordered history from memory_log."""
    inp = GetMemoryHistoryInput(project_id=project_id, key=key, limit=limit)
    history = await db.get_memory_history(inp.project_id, inp.key, inp.limit)
    return {
        "project_id": inp.project_id,
        "key": inp.key,
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
) -> dict:
    """Send an email using configured SMTP credentials."""
    import asyncio
    from src.email.sender import EmailSender
    
    sender = EmailSender()
    if not sender.is_configured():
        return {"status": "error", "message": "Email credentials not configured on the server"}
        
    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None, 
        lambda: sender.send_email(
            subject=subject,
            html_body=html_body,
            text_body=text_body,
            to=to,
            reply_to=reply_to
        )
    )
    
    if success:
        return {"status": "ok", "message": f"Email sent successfully to {', '.join(to)}"}
    else:
        return {"status": "error", "message": "Failed to send email. Check server logs."}

