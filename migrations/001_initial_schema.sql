-- Agent Tools — initial schema
-- Safe to re-run: all statements use IF NOT EXISTS guards.

-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE IF NOT EXISTS projects (
  id           BIGSERIAL   PRIMARY KEY,
  project_id   TEXT        NOT NULL UNIQUE,
  name         TEXT        NOT NULL,
  description  TEXT,
  created_at   TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS memory_state (
  id           BIGSERIAL   PRIMARY KEY,
  project_id   TEXT        NOT NULL REFERENCES projects(project_id),
  key          TEXT        NOT NULL,
  value        JSONB       NOT NULL,
  updated_at   TIMESTAMP   NOT NULL DEFAULT now(),

  UNIQUE (project_id, key)
);

CREATE TABLE IF NOT EXISTS memory_log (
  id           BIGSERIAL   PRIMARY KEY,
  project_id   TEXT        NOT NULL,
  key          TEXT        NOT NULL,
  value        JSONB       NOT NULL,
  created_at   TIMESTAMP   NOT NULL DEFAULT now()
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_memory_state_project
  ON memory_state(project_id);

CREATE INDEX IF NOT EXISTS idx_memory_log_project_key
  ON memory_log(project_id, key);

CREATE INDEX IF NOT EXISTS idx_memory_log_created_at
  ON memory_log(created_at);
