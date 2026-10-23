# Multi-stage Docker build for Meridian Health Claims MCP Server
# Runs as non-root user with read-only DB mount support and health check.

FROM ghcr.io/astral-sh/uv:0.6.5 AS uv

FROM python:3.12-slim-bookworm AS runner

# Install uv from the official uv image
COPY --from=uv /uv /uvx /bin/

# Create a non-root system user and group (UID 10001)
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy dependency specifications first to leverage layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into virtualenv without dev packages
RUN uv sync --frozen --no-dev --no-install-project

# Copy source code and database assets
COPY src/ src/
COPY schema.sql ./
COPY scripts/ scripts/
COPY README.md LICENSE ./

# Install project package into virtualenv
RUN uv sync --frozen --no-dev

# Prepare directories for read-only database mounts and append-only audit logs
RUN mkdir -p /app/data /app/audit && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    CLAIMS_DB_PATH="/app/data/claims.db" \
    CLAIMS_KEYS_FILE="/app/keys.json" \
    CLAIMS_AUDIT_PATH="/app/audit/audit.jsonl" \
    CLAIMS_HTTP_HOST="0.0.0.0" \
    CLAIMS_HTTP_PORT="8765"

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request, urllib.error; [exit(0) if getattr(e, 'code', None) in (200, 400, 401, 405) else exit(1) for e in [None]]; (lambda: (urllib.request.urlopen('http://127.0.0.1:8765/mcp') and exit(0)) if True else exit(1))()" || python3 -c "import urllib.request, urllib.error; try: urllib.request.urlopen('http://127.0.0.1:8765/mcp'); exit(0); except urllib.error.HTTPError as e: exit(0 if e.code in (200, 400, 401, 405) else 1); except Exception: exit(1)"

CMD ["python3", "-m", "claims_mcp", "--transport", "http"]
