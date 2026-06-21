FROM python:3.13-slim

# Install uv (only used at build time for dependency sync)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Install system dependencies if required for some python packages
# RUN apt-get update && apt-get install -y --no-install-recommends build-essential && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml uv.lock ./

# Sync dependencies — this populates .venv/ with pinned packages from uv.lock
RUN uv sync --frozen --no-dev

# Copy the rest of the application
COPY . .

# Make sure the venv's binaries are on PATH so we can call uvicorn directly
ENV PATH="/app/.venv/bin:${PATH}"
# Belt-and-suspenders: even if something invokes `uv run` later, do NOT re-sync
ENV UV_NO_SYNC=1

# Expose backend port
EXPOSE 8000

# IMPORTANT: call uvicorn directly from the baked-in venv to avoid `uv run`
# re-syncing dependencies on every container start. Calling `uv run` here would
# detect that the runtime env no longer matches uv.lock (because we built with
# `--no-dev` but uv tries to install dev tools like ruff/ty) and would re-download
# packages every restart, slowing startup and risking restart loops.
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
