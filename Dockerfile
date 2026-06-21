FROM python:3.13-slim

# Install uv (build-time only) and curl/wget (needed by Coolify's healthcheck
# and our own HEALTHCHECK below). python:3.13-slim ships without either.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY pyproject.toml uv.lock ./

# Sync dependencies — populates .venv/ with pinned packages from uv.lock.
# --compile-bytecode avoids a memory spike at runtime.
# --no-install-project avoids installing the project itself (we just want the deps).
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

# Copy the rest of the application
COPY . .

# Copy and mark the entrypoint as executable
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENV PATH="/app/.venv/bin:${PATH}"
ENV UV_NO_SYNC=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WEB_CONCURRENCY=1

EXPOSE 8000

# HEALTHCHECK using curl (Coolify also expects curl/wget to be in the image).
# --start-period gives the lifespan (DB migrations, embedding client init, ...)
# enough time to finish before failing the container.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:8000/api/health || exit 1

# Use entrypoint script (exec form) so uvicorn is PID 1 and receives SIGTERM
# directly. Without this, the shell is PID 1 and uvicorn never gets a
# graceful shutdown signal → "Waiting for connections to close" → forced kill
# → restart loop.
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
