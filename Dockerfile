FROM python:3.13-slim

# Install uv (only used at build time for dependency sync)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy requirements
COPY pyproject.toml uv.lock ./

# Sync dependencies — populates .venv/ with pinned packages from uv.lock.
# --compile-bytecode avoids a memory spike at runtime (Python pre-compiles
# .pyc files on first import which can blow past the cgroup limit on small VMs).
# --no-install-project avoids installing the project itself (we just want the deps).
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

# Copy the rest of the application
COPY . .

# Copy and mark the entrypoint as executable
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Make sure the venv's binaries are on PATH
ENV PATH="/app/.venv/bin:${PATH}"
# Belt-and-suspenders: even if something invokes `uv run` later, do NOT re-sync
ENV UV_NO_SYNC=1
# Don't write .pyc files at runtime (we already compiled them at build time)
ENV PYTHONDONTWRITEBYTECODE=1
# Don't buffer stdout/stderr — logs reach the platform in real time
ENV PYTHONUNBUFFERED=1
# Default to single worker; bump on Coolify if you have RAM headroom.
# Each worker duplicates the Python+app footprint, so 2 workers ≈ 2× RAM.
ENV WEB_CONCURRENCY=1

# Expose backend port
EXPOSE 8000

# HEALTHCHECK: so Coolify knows when the container is actually ready.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# Use entrypoint script (exec form) so uvicorn is PID 1 and receives SIGTERM
# directly. Without this, the shell is PID 1 and uvicorn never gets a
# graceful shutdown signal → "Waiting for connections to close" → forced kill
# → restart loop.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
