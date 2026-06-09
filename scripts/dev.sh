#!/usr/bin/env bash
set -euo pipefail

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ── Config ──
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── Cleanup on exit ──
PIDS=()
cleanup() {
  echo -e "\n${YELLOW}Shutting down...${NC}"
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  # Stop docker compose if we started it
  if [[ "${STARTED_DOCKER:-}" == "true" ]]; then
    docker compose -f "$PROJECT_DIR/docker-compose.yml" down --remove-orphans 2>/dev/null || true
  fi
  exit 0
}
trap cleanup INT TERM

log() {
  local prefix="$1"; shift
  echo -e "${prefix} $*"
}

# ── 1. Docker (PostgreSQL) ──
if docker compose -f "$PROJECT_DIR/docker-compose.yml" ps --status running 2>/dev/null | grep -q litreview-db; then
  log "${GREEN}[db]${NC}" "PostgreSQL already running"
else
  log "${BLUE}[db]${NC}" "Starting PostgreSQL..."
  docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d
  STARTED_DOCKER=true
fi

# Wait for DB to be ready
log "${BLUE}[db]${NC}" "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
  if docker exec litreview-db pg_isready -U litreview -q 2>/dev/null; then
    log "${GREEN}[db]${NC}" "PostgreSQL ready"
    break
  fi
  if [[ "$i" -eq 30 ]]; then
    log "${RED}[db]${NC}" "PostgreSQL failed to start"
    exit 1
  fi
  sleep 1
done

# ── 2. Backend (FastAPI) ──
log "${BLUE}[api]${NC}" "Starting FastAPI on port $BACKEND_PORT..."
cd "$PROJECT_DIR"
"$PROJECT_DIR/.venv/bin/uvicorn" app.main:app \
  --reload \
  --host 0.0.0.0 \
  --port "$BACKEND_PORT" \
  2>&1 | while IFS= read -r line; do echo -e "${BLUE}[api]${NC} $line"; done &
PIDS+=($!)

# ── 3. Frontend (Next.js) ──
log "${GREEN}[web]${NC}" "Starting Next.js on port $FRONTEND_PORT..."
cd "$PROJECT_DIR/frontend"
pnpm dev --port "$FRONTEND_PORT" \
  2>&1 | while IFS= read -r line; do echo -e "${GREEN}[web]${NC} $line"; done &
PIDS+=($!)

echo ""
echo -e "${GREEN}All services running:${NC}"
echo -e "  ${BLUE}API${NC}      http://localhost:$BACKEND_PORT"
echo -e "  ${BLUE}API docs${NC} http://localhost:$BACKEND_PORT/docs"
echo -e "  ${GREEN}Frontend${NC} http://localhost:$FRONTEND_PORT"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all${NC}"
echo ""

wait
