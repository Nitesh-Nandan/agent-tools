-- Agent Tools — database migration (memory tables)
-- Run once against your PostgreSQL database before starting the server.
-- Safe to re-run: all statements use IF NOT EXISTS / OR REPLACE guards.

-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS memory_state (
  project_id  TEXT        NOT NULL,
  key         TEXT        NOT NULL,
  value       JSONB       NOT NULL,
  updated_at  TIMESTAMP   NOT NULL DEFAULT now(),

  PRIMARY KEY (project_id, key)
);

CREATE TABLE IF NOT EXISTS memory_log (
  id          UUID        PRIMARY KEY,
  project_id  TEXT        NOT NULL,
  key         TEXT        NOT NULL,
  value       JSONB       NOT NULL,
  created_at  TIMESTAMP   NOT NULL DEFAULT now()
);

-- ============================================================
-- Indexes
-- ============================================================

-- Fast project-wide scans on memory_state
CREATE INDEX IF NOT EXISTS idx_memory_state_project
  ON memory_state(project_id);

-- Fast per-key history lookups
CREATE INDEX IF NOT EXISTS idx_memory_log_project_key
  ON memory_log(project_id, key);

-- Fast time-range queries / TTL cleanup (future)
CREATE INDEX IF NOT EXISTS idx_memory_log_created_at
  ON memory_log(created_at);
