FROM python:3.13-slim

# Install uv (only used at build time for dependency sync)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Install system dependencies if required for some python packages
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml uv.lock ./

# Sync dependencies — populates .venv/ with pinned packages from uv.lock.
# --compile-bytecode avoids a memory spike at runtime (Python pre-compiles .pyc
# files on first import which can blow past the cgroup limit on small instances).
# --no-install-project avoids installing the project itself (we just want the deps).
RUN uv sync --frozen --no-dev --no-install-project --compile-bytecode

# Copy the rest of the application
COPY . .

# Make sure the venv's binaries are on PATH so we can call uvicorn directly
ENV PATH="/app/.venv/bin:${PATH}"
# Belt-and-suspenders: even if something invokes `uv run` later, do NOT re-sync
ENV UV_NO_SYNC=1
# Don't write .pyc files at runtime (we already compiled them at build time)
ENV PYTHONDONTWRITEBYTECODE=1
# Don't buffer stdout/stderr — logs reach the platform in real time
ENV PYTHONUNBUFFERED=1
# Default workers = 2 (override with `WEB_CONCURRENCY` env var on the platform)
ENV WEB_CONCURRENCY=2

# Expose backend port
EXPOSE 8000

# Use a HEALTHCHECK so the platform knows when the container is actually ready.
# Without this, deploy platforms can mistakenly mark the container as healthy
# before the lifespan (DB migrations, embedding client init, …) finishes — and
# some will restart it if it doesn't respond on the health port fast enough.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

# IMPORTANT:
# 1) Call uvicorn directly from the baked-in venv (NOT `uv run uvicorn …`).
#    `uv run` re-syncs deps on every start, which causes a 5–10 s delay and
#    can crash if the registry is unreachable.
# 2) Set --limit-max-requests so each worker recycles after N requests.
#    Uvicorn leaks ~8–12 MB per 10 k requests; without this, the container
#    slowly grows in memory and gets OOMKilled after a few hours, then
#    restart-loops forever.
# 3) --timeout-graceful-shutdown ensures SIGTERM (sent by the platform on
#    restart/deploy) actually closes open SSE streams within a bounded time.
# 4) --workers 2 (via $WEB_CONCURRENCY) gives a small amount of parallelism
#    without doubling the RAM footprint.
CMD ["sh", "-c", "exec .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers ${WEB_CONCURRENCY:-2} \
    --limit-max-requests 10000 \
    --limit-max-requests-jitter 1000 \
    --timeout-keep-alive 30 \
    --timeout-graceful-shutdown 10 \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --log-level info"]
