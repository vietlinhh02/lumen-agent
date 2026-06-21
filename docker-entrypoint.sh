#!/bin/sh
set -e

# Defaults — overridden by env vars from Coolify / docker-compose / k8s
: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=1}"
: "${LOG_LEVEL:=info}"

# Coolify injects LOG_LEVEL=INFO (uppercase) but uvicorn only accepts
# lowercase. Lowercase it defensively to avoid "Invalid value for
# '--log-level'" → container crash loop.
LOG_LEVEL_LOWER=$(printf '%s' "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')

echo "[entrypoint] starting uvicorn on port ${PORT} with ${WEB_CONCURRENCY} worker(s), log_level=${LOG_LEVEL_LOWER}"

# `exec` so uvicorn replaces this shell as PID 1 and receives SIGTERM
# directly from the container runtime (Coolify / Docker).
exec .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers "${WEB_CONCURRENCY}" \
    --limit-max-requests 10000 \
    --limit-max-requests-jitter 1000 \
    --timeout-keep-alive 30 \
    --timeout-graceful-shutdown 10 \
    --proxy-headers \
    --forwarded-allow-ips='*' \
    --log-level "${LOG_LEVEL_LOWER}"
