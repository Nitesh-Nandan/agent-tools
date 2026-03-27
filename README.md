# Agent Tools

MCP server for agents: **PostgreSQL-backed memory** (`put_memory` / `get_memory` / `get_memory_history`) plus optional **`send_email`** (Gmail SMTP when configured).

---

## Architecture

```
Agent / LLM
    │
    │  MCP (stdio or SSE)
    ▼
src/server.py          ← FastMCP (memory tools + send_email)
    │
    ├─► src/memory/db.py   ← asyncpg pool + memory queries
    └─► src/email/         ← SMTP (optional)
    │
    ▼
PostgreSQL
  ├── memory_state     ← latest value per (project_id, key)
  └── memory_log       ← full immutable history
```

---

## Quick Reference (Makefile)

```bash
make install          # install deps
make create-schema    # create DB tables (idempotent)
make run              # start server (stdio)
make run-sse          # start server (SSE on :8000)
make docker-up        # docker compose up --build
make dump             # export tables → dumps/
make restore FILE=... # restore from a dump file
make stats            # row counts, sizes, recent writes
make reset            # ⚠ drop + recreate tables (dev only)
```

---

## Docker (recommended)

The easiest way to run the server — spins up PostgreSQL + the MCP server, runs migrations automatically.

```bash
make docker-up
```

The MCP server listens on port **8000 inside the container**; Compose publishes it as **`http://localhost:7075`** (SSE transport — e.g. `http://localhost:7075/sse` for MCP SSE clients).

> **Production tip**: override `POSTGRES_PASSWORD` / `DB_PASSWORD` via a `.env` file or secrets manager — don't commit credentials.

For the **`send_email`** tool in Docker, set **`EMAIL_USERNAME`** and **`EMAIL_PASSWORD`** in the same project **`.env`** file (see `.env.example`). Compose passes them into the **`mcp`** service container; leave them unset if you do not need email.

To connect to an **existing** PostgreSQL instance instead of the bundled one:

```bash
docker run --rm \
  -e DB_HOST=your-pg-host \
  -e DB_PORT=5432 \
  -e DB_NAME=agent_memory \
  -e DB_USER=agent \
  -e DB_PASSWORD=secret \
  -p 8000:8000 \
  agent-tools-image
```

(If you built with `docker compose build` instead of `make docker-build`, the image name is usually `agent-tools-mcp`.)

---

## Quick Start (local, no Docker)

```bash
# 1. Configure credentials
cp .env.example .env

# 2. Install deps + create tables
make install
make create-schema

# 3. Start the server
make run        # stdio — for Claude Desktop / MCP CLI
make run-sse    # SSE  — HTTP on :8000
```

---

## MCP Tools

### `put_memory`
Store or update a value. Atomically upserts the latest state **and** appends an immutable log entry in a single transaction.

```json
{
  "project_id": "acme:alice:send_email",
  "key": "email:last_sent",
  "value": { "timestamp": "2026-03-28T10:00:00Z", "to": "bob@example.com" }
}
```

### `get_memory`
Retrieve the current (latest) value for a key.

```json
{
  "project_id": "acme:alice:send_email",
  "key": "email:last_sent"
}
```

Response:
```json
{
  "found": true,
  "project_id": "acme:alice:send_email",
  "key": "email:last_sent",
  "value": { "timestamp": "2026-03-28T10:00:00Z" },
  "updated_at": "2026-03-28T10:00:00.123456"
}
```

### `get_memory_history`
Retrieve change history for a key, newest first.

```json
{
  "project_id": "acme:alice:send_email",
  "key": "email:last_sent",
  "limit": 10
}
```

### `send_email`
Send email via Gmail SMTP (HTML + plain text). Requires **`EMAIL_USERNAME`** and **`EMAIL_PASSWORD`** (app password) in the environment — see Docker / `.env.example`.

---

## Naming Conventions

These are enforced at the API level — invalid names are rejected.

| Field | Convention | Example |
|-------|-----------|---------|
| `key` | `<domain>:<entity>` or `<domain>:<entity>:<attribute>` | `email:last_sent`, `user:123:last_login` |
| `project_id` | `<org>:<user>:<workflow>` | `acme:alice:send_email` |

---

## Database Schema

```sql
-- Latest state (fast O(1) lookup)
memory_state (project_id, key) → value, updated_at

-- Immutable history log
memory_log (id UUID) → project_id, key, value, created_at
```

### Indexes
| Index | Purpose |
|-------|---------|
| `idx_memory_state_project` | Fast project-wide scans |
| `idx_memory_log_project_key` | Fast per-key history lookups |
| `idx_memory_log_created_at` | Time-range queries / future TTL cleanup |

---

## DB Scripts

All DB ops are in `scripts/manage.py` — uses `asyncpg` (already a project dep, no extra drivers).

```bash
make create-schema              # run migration
make dump                       # export to dumps/<timestamp>.sql
make restore FILE=dumps/x.sql  # restore from dump
make stats                      # health check
make reset                      # ⚠ dev only
```

---

## Future Upgrade Path

- **Concurrency safety**: Add `SELECT FOR UPDATE` or optimistic locking (`version` column) to `put_memory` when needed — the transactional structure already supports it
- **TTL / expiry**: Index on `created_at` is already in place for cleanup jobs
- **Multi-tenancy**: `project_id` convention `<org>:<user>:<workflow>` separates tenants by design
