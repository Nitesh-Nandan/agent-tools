# ── Stage 1: build deps with uv ──────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first (better layer caching)
COPY pyproject.toml uv.lock ./

# Install deps into /app/.venv — no editable install yet
RUN uv sync --frozen --no-install-project

# ── Stage 2: runtime image ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# psycopg / asyncpg need libpq at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY main.py .
COPY src/ src/
COPY migrations/ migrations/

# Make sure the venv is on PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose SSE port
EXPOSE 8000

# Default: run migrations then start the server in SSE mode
# Override CMD if you need stdio mode for a local MCP client:
#   docker run ... agent-kit-image python main.py --transport stdio
CMD ["sh", "-c", \
     "psql \"${DATABASE_URL}\" -f migrations/001_memory_tables.sql && \
      python main.py --transport sse --host 0.0.0.0 --port 8000"]
