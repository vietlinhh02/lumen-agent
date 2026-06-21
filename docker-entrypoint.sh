#!/bin/sh
set -e

# Use exec so uvicorn becomes PID 1 and receives SIGTERM directly from the
# container runtime (Coolify / Docker). Without `exec`, the shell is PID 1
# and uvicorn never gets a graceful shutdown signal → "Waiting for
# connections to close" hangs forever → container is killed forcefully.

# Defaults can be overridden by env vars from Coolify / docker-compose
: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=1}"
: "${LOG_LEVEL:=info}"

echo "[entrypoint] starting uvicorn on port ${PORT} with ${WEB_CONCURRENCY} worker(s)"

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
    --log-level "${LOG_LEVEL}"
