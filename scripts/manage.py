#!/usr/bin/env python3
"""
scripts/manage.py — Agent Tools DB management CLI

Uses only asyncpg (already a project dependency) — no extra drivers needed.

Commands:
  create-schema   Create DB tables and indexes (idempotent)
  reset           Drop and recreate tables (dev only)
  dump            Export memory_state + memory_log to a SQL file
  restore         Restore from a dump SQL file
  stats           Print row counts, table sizes, and recent activity

Usage:
  uv run scripts/manage.py create-schema
  uv run scripts/manage.py dump --out dumps/my_backup.sql
  uv run scripts/manage.py restore dumps/my_backup.sql
  uv run scripts/manage.py reset
  uv run scripts/manage.py stats
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

# ── Load .env from project root ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MIGRATIONS_DIR = ROOT / "migrations"
DUMPS_DIR = ROOT / "dumps"


# ── DB connection ─────────────────────────────────────────────────────────────

def _dsn() -> str:
    """Same defaults as src.config — avoids KeyError when .env omits keys."""
    user = os.environ.get("DB_USER", "postgres")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")
    name = os.environ.get("DB_NAME", "agent_memory")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_dsn())


# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_create_schema(_args) -> None:
    """Run the migration SQL — safe to re-run (IF NOT EXISTS guards)."""
    sql = (MIGRATIONS_DIR / "001_memory_tables.sql").read_text()
    conn = await _connect()
    try:
        print(f"▶  Running migration against {os.environ.get('DB_NAME')} ...")
        await conn.execute(sql)
        print("✓  Schema ready.")
    finally:
        await conn.close()


async def cmd_reset(_args) -> None:
    """Drop and recreate tables. Requires typing 'yes' to confirm."""
    print(f"⚠  WARNING: This will DROP all data in memory_state and memory_log")
    print(f"   Database : {os.environ.get('DB_NAME')} @ {os.environ.get('DB_HOST', 'localhost')}")
    answer = input("Type 'yes' to confirm: ").strip()
    if answer != "yes":
        print("Aborted.")
        return

    conn = await _connect()
    try:
        await conn.execute("DROP TABLE IF EXISTS memory_log;")
        await conn.execute("DROP TABLE IF EXISTS memory_state;")
        print("▶  Tables dropped.")
        sql = (MIGRATIONS_DIR / "001_memory_tables.sql").read_text()
        await conn.execute(sql)
        print("✓  Tables recreated.")
    finally:
        await conn.close()


async def cmd_dump(args) -> None:
    """
    Export memory_state and memory_log as plain SQL INSERT statements.
    No pg_dump required — the output file can be restored with cmd_restore.
    """
    DUMPS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    out_path = Path(args.out) if args.out else DUMPS_DIR / f"agent_memory_{timestamp}.sql"

    conn = await _connect()
    try:
        state_rows = await conn.fetch("SELECT project_id, key, value, updated_at FROM memory_state ORDER BY project_id, key")
        log_rows   = await conn.fetch("SELECT id, project_id, key, value, created_at FROM memory_log ORDER BY created_at")
    finally:
        await conn.close()

    lines = [
        f"-- Agent Tools dump — {datetime.now(timezone.utc).isoformat()}",
        f"-- memory_state rows : {len(state_rows)}",
        f"-- memory_log rows   : {len(log_rows)}",
        "",
        "BEGIN;",
        "",
        "-- memory_state",
    ]

    for r in state_rows:
        value_escaped = json.dumps(json.loads(r["value"])).replace("'", "''")
        lines.append(
            f"INSERT INTO memory_state (project_id, key, value, updated_at) VALUES "
            f"('{r['project_id']}', '{r['key']}', '{value_escaped}'::jsonb, '{r['updated_at'].isoformat()}')"
            f" ON CONFLICT (project_id, key) DO UPDATE SET value = EXCLUDED.value, updated_at = EXCLUDED.updated_at;"
        )

    lines += ["", "-- memory_log"]
    for r in log_rows:
        value_escaped = json.dumps(json.loads(r["value"])).replace("'", "''")
        lines.append(
            f"INSERT INTO memory_log (id, project_id, key, value, created_at) VALUES "
            f"('{r['id']}', '{r['project_id']}', '{r['key']}', '{value_escaped}'::jsonb, '{r['created_at'].isoformat()}')"
            f" ON CONFLICT (id) DO NOTHING;"
        )

    lines += ["", "COMMIT;", ""]
    out_path.write_text("\n".join(lines))
    print(f"✓  Dump saved: {out_path}")
    print(f"   memory_state : {len(state_rows)} rows")
    print(f"   memory_log   : {len(log_rows)} rows")


async def cmd_restore(args) -> None:
    """Restore from a SQL dump file produced by cmd_dump."""
    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"⚠  Restoring from {path} into '{os.environ.get('DB_NAME')}'")
    answer = input("Continue? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    sql = path.read_text()
    conn = await _connect()
    try:
        await conn.execute(sql)
        print("✓  Restore complete.")
    finally:
        await conn.close()


async def cmd_stats(_args) -> None:
    """Print row counts, sizes, top keys, and latest writes."""
    conn = await _connect()
    try:
        state_count = await conn.fetchval("SELECT COUNT(*) FROM memory_state")
        log_count   = await conn.fetchval("SELECT COUNT(*) FROM memory_log")

        sizes = await conn.fetch("""
            SELECT relname AS tbl,
                   pg_size_pretty(pg_total_relation_size(oid)) AS size
            FROM pg_class
            WHERE relname IN ('memory_state', 'memory_log')
            ORDER BY relname
        """)

        top_keys = await conn.fetch("""
            SELECT project_id, key, COUNT(*) AS entries, MAX(created_at) AS last_write
            FROM memory_log
            GROUP BY project_id, key
            ORDER BY entries DESC
            LIMIT 10
        """)

        recent = await conn.fetch("""
            SELECT project_id, key, created_at, value
            FROM memory_log
            ORDER BY created_at DESC
            LIMIT 5
        """)
    finally:
        await conn.close()

    # ── Print ──
    print("\n=== Row Counts ===")
    print(f"  memory_state : {state_count:,}")
    print(f"  memory_log   : {log_count:,}")

    print("\n=== Table Sizes ===")
    for r in sizes:
        print(f"  {r['tbl']:<20} {r['size']}")

    print("\n=== Top 10 Most Written Keys ===")
    if top_keys:
        for r in top_keys:
            print(f"  [{r['entries']:>5}x]  {r['project_id']}  /  {r['key']}  (last: {r['last_write']})")
    else:
        print("  (no data yet)")

    print("\n=== Latest 5 Writes ===")
    if recent:
        for r in recent:
            val_preview = str(r["value"])[:60]
            print(f"  {r['created_at']}  {r['project_id']} / {r['key']}  →  {val_preview}")
    else:
        print("  (no data yet)")

    print()


# ── CLI wiring ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Tools DB management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("create-schema", help="Create tables and indexes (idempotent)")
    sub.add_parser("reset",         help="Drop and recreate tables — DEV ONLY")
    sub.add_parser("stats",         help="Show row counts, sizes, and recent activity")

    p_dump = sub.add_parser("dump", help="Export tables to a SQL file")
    p_dump.add_argument("--out", metavar="FILE", help="Output path (default: dumps/agent_memory_<timestamp>.sql)")

    p_restore = sub.add_parser("restore", help="Restore from a SQL dump file")
    p_restore.add_argument("file", metavar="FILE", help="Path to the dump SQL file")

    args = parser.parse_args()

    handlers = {
        "create-schema": cmd_create_schema,
        "reset":         cmd_reset,
        "stats":         cmd_stats,
        "dump":          cmd_dump,
        "restore":       cmd_restore,
    }

    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
