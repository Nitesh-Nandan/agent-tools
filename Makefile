.DEFAULT_GOAL := help

# ── Variables ──────────────────────────────────────────────────────────────────
PYTHON   := uv run python
MANAGE   := $(PYTHON) scripts/manage.py

# ── Help ───────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@echo ""
	@echo "  Agent Tools — available targets"
	@echo ""
	@echo "  Setup"
	@echo "    make install          Install dependencies (uv sync)"
	@echo "    make create-schema    Create DB tables and indexes (idempotent)"
	@echo ""
	@echo "  Run"
	@echo "    make run              Start MCP server (stdio)"
	@echo "    make run-sse          Start MCP server (SSE on :8000)"
	@echo "    make docker-up        Build and start via docker compose"
	@echo "    make docker-down      Stop docker compose services"
	@echo "    make docker-build     Build a standalone Docker image (agent-tools-image)"
	@echo ""
	@echo "  DB Utilities"
	@echo "    make dump             Export tables to dumps/ (plain SQL)"
	@echo "    make restore FILE=... Restore from a dump file"
	@echo "    make stats            Show row counts, sizes, recent activity"
	@echo "    make reset            Drop + recreate tables  ⚠ DEV ONLY"
	@echo ""

# ── Setup ──────────────────────────────────────────────────────────────────────
.PHONY: install
install:
	uv sync

.PHONY: create-schema
create-schema:
	$(MANAGE) create-schema

# ── Run ────────────────────────────────────────────────────────────────────────
.PHONY: run
run:
	$(PYTHON) main.py --transport stdio

.PHONY: run-sse
run-sse:
	$(PYTHON) main.py --transport sse --host 0.0.0.0 --port 8000

.PHONY: docker-up
docker-up:
	docker compose up --build

.PHONY: docker-down
docker-down:
	docker compose down

.PHONY: docker-build
docker-build:
	docker build -t agent-tools-image .

# ── DB Utilities ───────────────────────────────────────────────────────────────
.PHONY: dump
dump:
	$(MANAGE) dump

.PHONY: restore
restore:
ifndef FILE
	$(error FILE is required — usage: make restore FILE=dumps/agent_memory_<timestamp>.sql)
endif
	$(MANAGE) restore $(FILE)

.PHONY: stats
stats:
	$(MANAGE) stats

.PHONY: reset
reset:
	$(MANAGE) reset
