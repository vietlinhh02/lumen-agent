SHELL := /usr/bin/env bash

.DEFAULT_GOAL := help

FRONTEND_DIR := frontend
BACKEND_HOST ?= 0.0.0.0
BACKEND_PORT ?= 8000
FRONTEND_PORT ?= 3000

.PHONY: help setup dev backend frontend test lint format typecheck check
.PHONY: test-backend lint-backend format-backend typecheck-backend
.PHONY: lint-frontend typecheck-frontend

help:
	@printf "Targets:\n"
	@printf "  setup              Install backend and frontend dependencies\n"
	@printf "  dev                Start backend and frontend together\n"
	@printf "  backend            Start FastAPI on port %s\n" "$(BACKEND_PORT)"
	@printf "  frontend           Start Next.js on port %s\n" "$(FRONTEND_PORT)"
	@printf "  check              Run backend lint, typecheck, and tests\n"
	@printf "  lint-frontend      Run frontend lint\n"
	@printf "  typecheck-frontend Run frontend TypeScript check\n"

setup:
	uv sync
	cd $(FRONTEND_DIR) && pnpm install --frozen-lockfile

dev:
	$(MAKE) -j2 backend frontend

backend:
	uv run uvicorn app.main:app \
		--reload \
		--host $(BACKEND_HOST) \
		--port $(BACKEND_PORT)

frontend:
	cd $(FRONTEND_DIR) && pnpm dev --port $(FRONTEND_PORT)

test: test-backend

test-backend:
	uv run pytest -q tests

lint: lint-backend

lint-backend:
	uv run ruff check app tests

lint-frontend:
	cd $(FRONTEND_DIR) && pnpm lint

format: format-backend

format-backend:
	uv run ruff format app tests

typecheck: typecheck-backend

typecheck-backend:
	uv run ty check app

typecheck-frontend:
	cd $(FRONTEND_DIR) && pnpm exec tsc --noEmit

check: lint-backend typecheck-backend test-backend
