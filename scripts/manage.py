#!/usr/bin/env python3
"""
scripts/manage.py — Agent Kit DB management CLI

Commands:
  create-schema   Create DB tables and indexes (idempotent)
  reset           Drop and recreate all tables (dev only)
  dump            Export all tables to a SQL file
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

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MIGRATIONS_DIR = ROOT / "migrations"
DUMPS_DIR = ROOT / "dumps"


# ── DB connection ──────────────────────────────────────────────────────────────

def _dsn() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("ERROR: DATABASE_URL is not set. Add it to your .env file.")
    return url


async def _connect() -> asyncpg.Connection:
    return await asyncpg.connect(_dsn())


# ── Commands ───────────────────────────────────────────────────────────────────

async def cmd_create_schema(_args) -> None:
    """Run all migrations in order — safe to re-run (IF NOT EXISTS guards)."""
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    conn = await _connect()
    try:
        for path in migrations:
            print(f"▶  {path.name} ...")
            await conn.execute(path.read_text())
        print("✓  Schema ready.")
    finally:
        await conn.close()


async def cmd_reset(_args) -> None:
    """Drop and recreate all tables. Requires typing 'yes' to confirm."""
    print("⚠  WARNING: This will DROP all data in projects, memory_state, memory_log")
    print(f"   DATABASE_URL: {_dsn()}")
    answer = input("Type 'yes' to confirm: ").strip()
    if answer != "yes":
        print("Aborted.")
        return

    conn = await _connect()
    try:
        await conn.execute("DROP TABLE IF EXISTS memory_log;")
        await conn.execute("DROP TABLE IF EXISTS memory_state;")
        await conn.execute("DROP TABLE IF EXISTS projects;")
        print("▶  Tables dropped.")
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(path.read_text())
        print("✓  Tables recreated.")
    finally:
        await conn.close()


async def cmd_backup(args) -> None:
    """Schema + data in one SQL file. Apply to a fresh DB to migrate everything."""
    out_path = Path(args.out)

    conn = await _connect()
    try:
        project_rows = await conn.fetch(
            "SELECT project_id, name, description, created_at FROM projects ORDER BY created_at"
        )
        state_rows = await conn.fetch(
            "SELECT project_id, key, value, updated_at FROM memory_state ORDER BY project_id, key"
        )
        log_rows = await conn.fetch(
            "SELECT project_id, key, value, created_at FROM memory_log ORDER BY created_at"
        )
    finally:
        await conn.close()

    schema = (MIGRATIONS_DIR / "001_initial_schema.sql").read_text().strip()

    lines = [
        f"-- Agent Kit backup — {datetime.now(timezone.utc).isoformat()}",
        f"-- projects     : {len(project_rows)} rows",
        f"-- memory_state : {len(state_rows)} rows",
        f"-- memory_log   : {len(log_rows)} rows",
        "",
        "-- schema",
        schema,
        "",
        "-- data",
        "BEGIN;",
        "",
        "-- projects",
    ]

    for r in project_rows:
        name = r["name"].replace("'", "''")
        desc = r["description"].replace("'", "''") if r["description"] else None
        desc_sql = f"'{desc}'" if desc is not None else "NULL"
        lines.append(
            f"INSERT INTO projects (project_id, name, description, created_at) VALUES "
            f"('{r['project_id']}', '{name}', {desc_sql}, "
            f"'{r['created_at'].isoformat()}') ON CONFLICT DO NOTHING;"
        )

    lines += ["", "-- memory_state"]
    for r in state_rows:
        val = json.dumps(json.loads(r["value"])).replace("'", "''")
        lines.append(
            f"INSERT INTO memory_state (project_id, key, value, updated_at) VALUES "
            f"('{r['project_id']}', '{r['key']}', '{val}'::jsonb, "
            f"'{r['updated_at'].isoformat()}') ON CONFLICT DO NOTHING;"
        )

    lines += ["", "-- memory_log"]
    for r in log_rows:
        val = json.dumps(json.loads(r["value"])).replace("'", "''")
        lines.append(
            f"INSERT INTO memory_log (project_id, key, value, created_at) VALUES "
            f"('{r['project_id']}', '{r['key']}', '{val}'::jsonb, "
            f"'{r['created_at'].isoformat()}');"
        )

    lines += ["", "COMMIT;", ""]
    out_path.write_text("\n".join(lines))
    print(f"✓  {out_path}")
    print(f"   projects     : {len(project_rows)} rows")
    print(f"   memory_state : {len(state_rows)} rows")
    print(f"   memory_log   : {len(log_rows)} rows")
    print(f"\nTo restore: psql $DATABASE_URL < {out_path}")


async def cmd_restore(args) -> None:
    """Restore from a SQL dump file produced by cmd_dump."""
    path = Path(args.file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"⚠  Restoring from {path}")
    answer = input("Continue? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        return

    conn = await _connect()
    try:
        await conn.execute(path.read_text())
        print("✓  Restore complete.")
    finally:
        await conn.close()


async def cmd_stats(_args) -> None:
    """Print row counts, sizes, top keys, and latest writes."""
    conn = await _connect()
    try:
        project_count = await conn.fetchval("SELECT COUNT(*) FROM projects")
        state_count = await conn.fetchval("SELECT COUNT(*) FROM memory_state")
        log_count = await conn.fetchval("SELECT COUNT(*) FROM memory_log")

        sizes = await conn.fetch("""
            SELECT relname AS tbl,
                   pg_size_pretty(pg_total_relation_size(oid)) AS size
            FROM pg_class
            WHERE relname IN ('projects', 'memory_state', 'memory_log')
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

    print("\n=== Row Counts ===")
    print(f"  projects     : {project_count:,}")
    print(f"  memory_state : {state_count:,}")
    print(f"  memory_log   : {log_count:,}")

    print("\n=== Table Sizes ===")
    for r in sizes:
        print(f"  {r['tbl']:<20} {r['size']}")

    print("\n=== Top 10 Most Written Keys ===")
    if top_keys:
        for r in top_keys:
            print(
                f"  [{r['entries']:>5}x]  {r['project_id']}  /  {r['key']}"
                f"  (last: {r['last_write']})"
            )
    else:
        print("  (no data yet)")

    print("\n=== Latest 5 Writes ===")
    if recent:
        for r in recent:
            val_preview = str(r["value"])[:60]
            print(
                f"  {r['created_at']}  {r['project_id']} / {r['key']}"
                f"  →  {val_preview}"
            )
    else:
        print("  (no data yet)")

    print()


# ── CLI wiring ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Kit DB management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("create-schema", help="Create tables and indexes (idempotent)")
    sub.add_parser("reset", help="Drop and recreate tables — DEV ONLY")
    sub.add_parser("stats", help="Show row counts, sizes, and recent activity")

    p_backup = sub.add_parser("backup", help="Export schema + data to a single SQL file")
    p_backup.add_argument("out", metavar="FILE", help="Output path")

    p_restore = sub.add_parser("restore", help="Restore from a backup SQL file")
    p_restore.add_argument("file", metavar="FILE", help="Path to the backup SQL file")

    args = parser.parse_args()

    handlers = {
        "create-schema": cmd_create_schema,
        "reset": cmd_reset,
        "stats": cmd_stats,
        "backup": cmd_backup,
        "restore": cmd_restore,
    }

    asyncio.run(handlers[args.command](args))


if __name__ == "__main__":
    main()
