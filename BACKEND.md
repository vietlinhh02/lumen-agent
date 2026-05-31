# Backend

FastAPI backend scaffold for the AI Literature Review Assistant.

## Quick Start

From the repository root:

```bash
make setup
make backend
```

The API starts at `http://localhost:8010`.

Health check:

```bash
curl http://localhost:8010/api/health
```

## Local Commands

```bash
make test
make lint
make typecheck
make check
```
